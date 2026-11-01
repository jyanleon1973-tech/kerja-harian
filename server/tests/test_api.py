"""API とジョブの結合テスト。
- 人物のいない合成動画: パイプラインが完走し、検出率 0 で結果が返ることを確認（モデルのダウンロードは必要）。
- 環境変数 SKI_TEST_VIDEO に人物が映った動画を指定すると、検出・指標・書き出しまで確認する。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SKI_POSE_MODEL", "lite")
    config.reset_settings(data_dir=tmp_path / "data", model_dir=Path(os.environ.get("SKI_MODEL_DIR", str(tmp_path / "models"))), job_timeout_s=600)
    from app.main import app
    with TestClient(app) as c:
        yield c


def synthetic_video(path: Path, seconds=1.0, fps=30, size=(320, 240)) -> Path:
    """人物のいない合成動画（動く箱）。ffmpeg があれば H.264、なければ OpenCV の mp4v。"""
    import shutil, subprocess
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=0xEBEBEB:s={size[0]}x{size[1]}:r={fps}:d={seconds}",
                        "-vf", "drawbox=x='20+90*t':y=150:w=40:h=50:color=0x5A5A5A:t=fill", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True)
        return path
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for k in range(int(seconds * fps)):
        img = np.full((size[1], size[0], 3), 235, np.uint8)
        cv2.rectangle(img, (20 + k * 3, 150), (60 + k * 3, 200), (90, 90, 90), -1)
        w.write(img)
    w.release()
    return path


def wait_done(client, jid, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/analysis/jobs/{jid}").json()
        if j["status"] in ("done", "failed", "canceled"):
            return j
        time.sleep(0.5)
    raise AssertionError("timeout")


def test_upload_rejects_bad_type(client, tmp_path):
    p = tmp_path / "x.txt"; p.write_text("hello")
    r = client.post("/api/uploads", files={"file": ("x.txt", p.read_bytes(), "text/plain")})
    assert r.status_code == 415


def test_job_requires_existing_upload(client):
    r = client.post("/api/analysis/jobs", json={"upload_key": "uploads/none.mp4"})
    assert r.status_code == 404


def test_job_lifecycle_on_video_without_person(client, tmp_path):
    vid = synthetic_video(tmp_path / "blank.mp4")
    r = client.post("/api/uploads", files={"file": ("blank.mp4", vid.read_bytes(), "video/mp4")})
    assert r.status_code == 200, r.text
    key = r.json()["upload_key"]
    r = client.post("/api/analysis/jobs", json={"upload_key": key, "params": {"fps": 10, "pose_model": "lite"}})
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    j = wait_done(client, jid)
    assert j["status"] == "done", j.get("error")
    assert [s["stage"] for s in j["stages"]] == ["decode", "perframe", "temporal", "camera", "turns", "metrics", "confidence", "results"]
    assert "pose" in j["model_versions"]
    res = client.get(f"/api/analysis/jobs/{jid}/results").json()
    assert res["schema"] == "ski-analysis/2" and res["quality"]["detect_rate"] == 0 and res["frame_count"] >= 8
    fr = client.get(f"/api/analysis/jobs/{jid}/frames", params={"limit": 3, "fields": "src,turn"}).json()
    assert fr["count"] == 3 and fr["frames"][0]["src"] is None and fr["frames"][0]["turn"] is None
    st = client.get(f"/api/analysis/jobs/{jid}/stages/2").json()
    assert st["summary"]["detected"] == 0
    # 手動修正の保存（学習利用は既定で不可）
    r = client.patch(f"/api/analysis/jobs/{jid}/corrections", json={"corrections": [{"frame_i": 0, "kind": "turn", "data": {"turn": -1}}]})
    assert r.status_code == 200
    cors = client.get(f"/api/analysis/jobs/{jid}/corrections").json()
    assert len(cors) == 1 and cors[0]["training_consent"] is False
    # 書き出し（検出なしでも元動画を出す）
    r = client.post(f"/api/analysis/jobs/{jid}/exports", json={"speed": 1.0})
    assert r.status_code == 201
    eid = r.json()["id"]
    for _ in range(120):
        e = client.get(f"/api/analysis/jobs/{jid}/exports/{eid}").json()
        if e["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert e["status"] == "done", e.get("error")
    assert client.get(e["url"]).status_code == 200


@pytest.mark.skipif(not os.environ.get("SKI_TEST_VIDEO"), reason="SKI_TEST_VIDEO（人物の映った動画）が未指定")
def test_job_on_real_person_video(client):
    vid = Path(os.environ["SKI_TEST_VIDEO"])
    r = client.post("/api/uploads", files={"file": (vid.name, vid.read_bytes(), "video/mp4")})
    key = r.json()["upload_key"]
    jid = client.post("/api/analysis/jobs", json={"upload_key": key, "params": {"fps": 10, "pose_model": "lite", "end_s": 4}}).json()["id"]
    j = wait_done(client, jid)
    assert j["status"] == "done", j.get("error")
    res = client.get(f"/api/analysis/jobs/{jid}/results", params={"include_frames": True}).json()
    assert res["quality"]["detect_rate"] > 0.8, res["quality"]
    f = next(f for f in res["frames"] if f["src"] == "det")
    assert len(f["lm"]) == 33 and f["metrics"] and f["q"][11] > 0.5
    assert res["view"] in ("side", "front", "back", "oblique")
    r = client.post(f"/api/analysis/jobs/{jid}/exports", json={"speed": 0.5, "to_i": 10})
    eid = r.json()["id"]
    for _ in range(240):
        e = client.get(f"/api/analysis/jobs/{jid}/exports/{eid}").json()
        if e["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert e["status"] == "done", e.get("error")
