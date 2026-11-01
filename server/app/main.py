"""FastAPI アプリ。§13 の API に加え、ローカル用のアップロード・ファイル配信を持つ。
起動: uvicorn app.main:app --host 0.0.0.0 --port 8000  （server/ ディレクトリで）"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .db import Database, new_id
from .jobs import JobManager
from .storage import LocalStorage, S3Storage


def make_storage(s):
    if os.environ.get("SKI_S3_BUCKET"):
        return S3Storage(os.environ["SKI_S3_BUCKET"], os.environ.get("SKI_S3_PREFIX", ""), os.environ.get("SKI_S3_ENDPOINT"), os.environ.get("SKI_S3_REGION"), s.data_dir / "s3cache")
    return LocalStorage(s.data_dir / "storage")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.settings = s
    app.state.db = Database(s.db_path)
    app.state.storage = make_storage(s)
    app.state.jobs = JobManager(app.state.db, app.state.storage, s)
    app.state.jobs.start()
    yield
    app.state.jobs.stop()


app = FastAPI(title="Ski Motion Analysis API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("SKI_CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


# ---------- schemas ----------
class JobParams(BaseModel):
    fps: float = Field(30, ge=1, le=240, description="解析コマ数/秒")
    start_s: float = Field(0, ge=0)
    end_s: Optional[float] = Field(None, ge=0)
    pose_backend: str = Field("mediapipe", pattern="^(mediapipe|rtmpose)$")
    pose_model: str = Field("heavy", pattern="^(lite|full|heavy)$")
    sensitivity: float = Field(0.3, ge=0.05, le=0.9)
    view: str = Field("auto", pattern="^(auto|side|front|back|oblique)$")
    target: Optional[list[float]] = Field(None, description="対象選手の位置 [x,y]（0-1）")
    roll_deg: float = Field(0, ge=-45, le=45)
    ski_length_m: float = Field(1.65, ge=1.0, le=2.3, description="3D 表示に使う板の長さ（SL 約1.65、GS 約1.9）")


class JobCreate(BaseModel):
    upload_key: str
    params: JobParams = Field(default_factory=JobParams)


class CorrectionIn(BaseModel):
    frame_i: Optional[int] = None
    kind: str = Field(..., description="joint | ski | swap_lr | target | turn | switch")
    data: dict[str, Any] = Field(default_factory=dict)
    training_consent: bool = Field(False, description="この修正と該当コマを教師データとして利用してよいか（既定: 不可）")
    author: Optional[str] = None


class CorrectionsPatch(BaseModel):
    corrections: list[CorrectionIn]


class FollowSettings(BaseModel):
    mode: str = Field("normal", pattern="^(normal|follow|zoom|skis)$", description="normal: 全体, follow: 追尾, zoom: 追尾+自動ズーム, skis: 板追尾")
    framing: str = Field("full", pattern="^(full|body|upper|skis)$")
    target_frac: float = Field(0.75, ge=0.4, le=0.95)
    zoom_mult: float = Field(1.0, ge=0.5, le=2.0)
    smooth: float = Field(0.5, ge=0.0, le=1.0)
    center_y: float = Field(0.0, ge=-0.3, le=0.3)
    max_zoom: float = Field(4.0, ge=1.0, le=6.0)


class ExportCreate(BaseModel):
    speed: float = Field(1.0, ge=0.05, le=1.0)
    from_i: int = 0
    to_i: Optional[int] = None
    overlay: dict[str, bool] = Field(default_factory=lambda: {"skel": True, "lines": True, "cog": True, "ski": True, "text": True, "unsure": True})
    follow: FollowSettings = Field(default_factory=FollowSettings)


# ---------- uploads ----------
@app.post("/api/uploads")
async def upload(request: Request, file: UploadFile = File(...)):
    s = request.app.state.settings
    ext = Path(file.filename or "").suffix.lower()
    if ext not in s.allowed_extensions or (file.content_type and file.content_type not in s.allowed_video_types):
        raise HTTPException(415, f"対応していない形式です: {file.filename} ({file.content_type})")
    key = f"uploads/{new_id('up')}{ext}"
    try:
        n = request.app.state.storage.put_stream(key, file.file, file.content_type, max_bytes=s.max_upload_mb * 1024 * 1024)
    except ValueError:
        raise HTTPException(413, f"上限 {s.max_upload_mb} MB を超えています")
    return {"upload_key": key, "bytes": n}


@app.post("/api/uploads/presign")
async def presign(request: Request, filename: str = Query(...), content_type: str = Query("video/mp4")):
    s = request.app.state.settings
    ext = Path(filename).suffix.lower()
    if ext not in s.allowed_extensions:
        raise HTTPException(415, "対応していない形式です")
    key = f"uploads/{new_id('up')}{ext}"
    return request.app.state.storage.presign_upload(key, content_type)


@app.put("/api/uploads/{key:path}")
async def upload_put(request: Request, key: str):
    """ローカルストレージ用の署名なし PUT（本番では S3 の署名付き URL を使う）。"""
    s = request.app.state.settings
    if not key.startswith("uploads/") or Path(key).suffix.lower() not in s.allowed_extensions:
        raise HTTPException(400, "invalid key")
    body = await request.body()
    if len(body) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "too large")
    request.app.state.storage.put_bytes(key, body, request.headers.get("content-type"))
    return {"upload_key": key, "bytes": len(body)}


# ---------- jobs ----------
@app.post("/api/analysis/jobs", status_code=201)
async def create_job(request: Request, body: JobCreate):
    st = request.app.state.storage
    if not st.exists(body.upload_key):
        raise HTTPException(404, "アップロードが見つかりません")
    job = request.app.state.jobs.submit(body.upload_key, body.params.model_dump())
    return _job_view(job)


@app.get("/api/analysis/jobs")
async def list_jobs(request: Request, limit: int = 50):
    return [_job_view(j) for j in request.app.state.db.list_jobs(limit)]


@app.get("/api/analysis/jobs/{job_id}")
async def get_job(request: Request, job_id: str):
    job = request.app.state.db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    v = _job_view(job)
    v["stages"] = request.app.state.db.stage_outputs(job_id)
    return v


@app.delete("/api/analysis/jobs/{job_id}")
async def cancel_job(request: Request, job_id: str):
    if not request.app.state.db.get_job(job_id):
        raise HTTPException(404, "job not found")
    request.app.state.jobs.cancel(job_id)
    return {"ok": True}


@app.get("/api/analysis/jobs/{job_id}/results")
async def get_results(request: Request, job_id: str, include_frames: bool = False):
    job = _done_job(request, job_id)
    res = request.app.state.storage.get_json(job["result_key"])
    if not include_frames:
        res = {k: v for k, v in res.items() if k != "frames"}
        res["frame_count"] = len(request.app.state.storage.get_json(job["result_key"])["frames"])
    res["corrections"] = request.app.state.db.corrections(job_id)
    return res


@app.get("/api/analysis/jobs/{job_id}/frames")
async def get_frames(request: Request, job_id: str, start: int = 0, limit: int = Query(2000, le=20000), fields: Optional[str] = None):
    job = _done_job(request, job_id)
    frames = request.app.state.storage.get_json(job["result_key"])["frames"][start:start + limit]
    if fields:
        keep = set(fields.split(",")) | {"i", "t"}
        frames = [{k: v for k, v in f.items() if k in keep} for f in frames]
    return {"start": start, "count": len(frames), "frames": frames}


@app.get("/api/analysis/jobs/{job_id}/stages/{seq}")
async def get_stage(request: Request, job_id: str, seq: int):
    for st in request.app.state.db.stage_outputs(job_id):
        if st["seq"] == seq:
            return request.app.state.storage.get_json(st["key"])
    raise HTTPException(404, "stage not found")


@app.patch("/api/analysis/jobs/{job_id}/corrections")
async def patch_corrections(request: Request, job_id: str, body: CorrectionsPatch):
    if not request.app.state.db.get_job(job_id):
        raise HTTPException(404, "job not found")
    saved = [request.app.state.db.add_correction(job_id, c.model_dump(exclude={"training_consent", "author"}), c.training_consent, c.author) for c in body.corrections]
    return {"saved": saved}


@app.get("/api/analysis/jobs/{job_id}/corrections")
async def get_corrections(request: Request, job_id: str):
    return request.app.state.db.corrections(job_id)


@app.post("/api/analysis/jobs/{job_id}/exports", status_code=201)
async def create_export(request: Request, job_id: str, body: ExportCreate):
    _done_job(request, job_id)
    return request.app.state.jobs.submit_export(job_id, body.model_dump())


@app.get("/api/analysis/jobs/{job_id}/exports/{export_id}")
async def get_export(request: Request, job_id: str, export_id: str):
    exp = request.app.state.db.get_export(export_id)
    if not exp or exp["job_id"] != job_id:
        raise HTTPException(404, "export not found")
    if exp.get("key"):
        exp["url"] = request.app.state.storage.url_for(exp["key"])
    return exp


@app.get("/files/{key:path}")
async def get_file(request: Request, key: str):
    st = request.app.state.storage
    if not isinstance(st, LocalStorage) or not st.exists(key):
        raise HTTPException(404, "not found")
    return FileResponse(st.local_path(key))


@app.get("/api/health")
async def health(request: Request):
    s = request.app.state.settings
    return {"ok": True, "time": time.time(), "pose_backend": s.pose_backend, "worker_mode": s.worker_mode, "max_concurrent_jobs": s.max_concurrent_jobs}


@app.post("/api/admin/cleanup")
async def cleanup(request: Request):
    return {"deleted": request.app.state.jobs.cleanup()}


def _job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {k: job.get(k) for k in ("id", "status", "progress", "stage", "message", "created_at", "updated_at", "started_at", "finished_at", "params", "error", "attempts", "model_versions", "pipeline_version", "result_key")}


def _done_job(request: Request, job_id: str) -> dict[str, Any]:
    job = request.app.state.db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] != "done":
        raise HTTPException(409, f"job is {job['status']}")
    return job
