"""ジョブ管理。Phase 2 は同一プロセスのワーカースレッドで実行（inline）。
GPU ワーカーを別プロセス/別マシンにする場合は、同じ DB のキューを取りに行く external モードを追加する
（claim_next_job → run → update）。タイムアウト、再試行、同時実行数、古いジョブの削除を持つ。"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database
from .pipeline.base import PIPELINE_VERSION, Canceled, Context
from .pipeline.run import run_job
from .pipeline.render import render_video
from .pipeline.track import plan_camera
from .storage import Storage


class JobManager:
    def __init__(self, db: Database, storage: Storage, settings: Settings):
        self.db = db; self.storage = storage; self.s = settings
        self._wake = threading.Event(); self._stop = threading.Event()
        self._cancel: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._exports: list[tuple[str, str]] = []

    # ---- ライフサイクル ----
    def start(self):
        for k in range(max(1, self.s.max_concurrent_jobs)):
            th = threading.Thread(target=self._loop, name=f"ski-worker-{k}", daemon=True); th.start(); self._threads.append(th)
        threading.Thread(target=self._export_loop, name="ski-export", daemon=True).start()

    def stop(self):
        self._stop.set(); self._wake.set()

    # ---- API 側から ----
    def submit(self, video_key: str, params: dict[str, Any]) -> dict[str, Any]:
        job = self.db.create_job(video_key, params, PIPELINE_VERSION)
        self._wake.set()
        return job

    def cancel(self, job_id: str) -> None:
        self._cancel.add(job_id)
        job = self.db.get_job(job_id)
        if job and job["status"] == "queued":
            self.db.update_job(job_id, status="canceled", finished_at=time.time(), message="キャンセル")

    def submit_export(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        exp = self.db.create_export(job_id, params)
        self._exports.append((exp["id"], job_id)); self._wake.set()
        return exp

    def cleanup(self) -> int:
        """保持期間を過ぎたジョブの動画・結果を削除。"""
        n = 0
        for job in self.db.old_jobs(time.time() - self.s.retention_days * 86400):
            try:
                self.storage.delete_prefix(f"jobs/{job['id']}")
                if job.get("video_key"):
                    self.storage.delete_prefix(job["video_key"])
                self.db.delete_job(job["id"]); n += 1
            except Exception:
                pass
        return n

    # ---- ワーカー ----
    def _loop(self):
        while not self._stop.is_set():
            job = None
            if self.db.running_count() < self.s.max_concurrent_jobs:
                job = self.db.claim_next_job()
            if not job:
                self._wake.wait(timeout=1.0); self._wake.clear(); continue
            self._run_with_timeout(job)

    def _run_with_timeout(self, job: dict[str, Any]):
        jid = job["id"]
        result: dict[str, Any] = {}
        err: list[str] = []

        def progress(p, stage, msg):
            self.db.update_job(jid, progress=round(float(p), 4), stage=stage, message=msg)

        def should_cancel():
            return jid in self._cancel or self._stop.is_set() or (time.time() - (job.get("started_at") or time.time())) > self.s.job_timeout_s

        def target():
            try:
                video_path = str(self.storage.local_path(job["video_key"]))
                ctx = Context(job_id=jid, params=job["params"] or {}, storage=self.storage, video_path=video_path, model_dir=str(self.s.model_dir), progress=progress, should_cancel=should_cancel)
                out = run_job(ctx, on_stage_done=lambda r: self.db.add_stage_output(jid, r.seq, r.stage, r.key, r.duration_ms, r.summary))
                result.update(out)
            except Canceled:
                err.append("__canceled__")
            except Exception as e:
                err.append(f"{e}\n{traceback.format_exc()}")

        th = threading.Thread(target=target, daemon=True); th.start(); th.join(self.s.job_timeout_s + 30)
        if th.is_alive():
            err.append("timeout")
        if err and err[0] == "__canceled__":
            self.db.update_job(jid, status="canceled", finished_at=time.time(), message="キャンセル"); self._cancel.discard(jid); return
        if err:
            attempts = (self.db.get_job(jid) or {}).get("attempts", 1)
            if attempts < self.s.job_max_attempts and err[0] != "timeout":
                self.db.update_job(jid, status="queued", error=err[0][:4000], message=f"失敗のため再試行（{attempts}/{self.s.job_max_attempts}）")
                self._wake.set()
            else:
                self.db.update_job(jid, status="failed", finished_at=time.time(), error=err[0][:4000], message="失敗")
            return
        self.db.update_job(jid, status="done", finished_at=time.time(), progress=1.0, stage="done", message="完了",
                           result_key=result["result_key"], model_versions=result["model_versions"])

    def _export_loop(self):
        while not self._stop.is_set():
            if not self._exports:
                time.sleep(0.5); continue
            eid, jid = self._exports.pop(0)
            try:
                self.db.update_export(eid, status="running")
                job = self.db.get_job(jid); exp = self.db.get_export(eid)
                if not job or job["status"] != "done":
                    raise RuntimeError("解析が完了していません")
                res = self.storage.get_json(job["result_key"])
                p = exp["params"]
                frames = [{"i": f["i"], "t": f["t"], "kpS": f["lm"], "q": f["q"], "ski": f["ski"]} for f in res["frames"]]
                metrics = [({"M": f["metrics"], **f["geom"]} if f.get("metrics") and f.get("geom") else None) for f in res["frames"]]
                a = int(p.get("from_i") or 0); b = len(frames) - 1 if p.get("to_i") is None else int(p["to_i"])
                sel = [k for k, f in enumerate(frames) if a <= f["i"] <= b]
                sub = lambda arr: [arr[k] for k in sel]
                out_path = Path(self.s.data_dir) / "tmp" / f"{eid}.mp4"; out_path.parent.mkdir(parents=True, exist_ok=True)
                follow = p.get("follow") or {}
                cam = None
                if follow.get("mode", "normal") != "normal":
                    tracks = [f.get("track") for f in res["frames"]]
                    cam = sub(plan_camera(tracks, 1.0 / res["sample_fps"], res["video"]["width"], res["video"]["height"], follow))
                info = render_video(str(self.storage.local_path(job["video_key"])), str(out_path), sub(frames), sub(metrics), res["view"],
                                    sub([f["turn"] for f in res["frames"]]), sub([f["phase"] for f in res["frames"]]), res["sample_fps"],
                                    float(res["params"].get("start_s") or 0), res["params"].get("end_s"), speed=float(p.get("speed", 1.0)), opts=p.get("overlay", {}), camera=cam)
                key = f"jobs/{jid}/exports/{eid}.mp4"
                self.storage.put_file(key, out_path, "video/mp4"); out_path.unlink(missing_ok=True)
                self.db.update_export(eid, status="done", key=key)
            except Exception as e:
                self.db.update_export(eid, status="failed", error=str(e)[:2000])
