"""動画のメタ情報と、実タイムスタンプに基づくフレーム抽出（可変フレームレート対応）。
フレーム画像は保存せず、必要な段階がストリームで読む。"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Iterator

import cv2
import numpy as np


def probe(video_path: str) -> dict[str, Any]:
    """ffprobe があれば使い、なければ OpenCV のメタ情報で代用。"""
    info: dict[str, Any] = {}
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration,codec_name:stream_tags=rotate:format=duration",
                 "-of", "json", video_path], capture_output=True, text=True, timeout=60).stdout
            j = json.loads(out)
            s = (j.get("streams") or [{}])[0]
            def fr(x):
                try:
                    a, b = x.split("/"); return float(a) / float(b) if float(b) else 0.0
                except Exception:
                    return 0.0
            info = {"width": s.get("width"), "height": s.get("height"), "codec": s.get("codec_name"),
                    "r_frame_rate": fr(s.get("r_frame_rate", "0/1")), "avg_frame_rate": fr(s.get("avg_frame_rate", "0/1")),
                    "nb_frames": int(s["nb_frames"]) if str(s.get("nb_frames", "")).isdigit() else None,
                    "duration": float(s.get("duration") or j.get("format", {}).get("duration") or 0),
                    "rotate": int((s.get("tags") or {}).get("rotate", 0) or 0)}
        except Exception:
            info = {}
    cap = cv2.VideoCapture(video_path)
    try:
        info.setdefault("width", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        info.setdefault("height", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        info.setdefault("avg_frame_rate", float(cap.get(cv2.CAP_PROP_FPS) or 0))
        if not info.get("duration"):
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT); f = cap.get(cv2.CAP_PROP_FPS)
            info["duration"] = float(n / f) if f else 0.0
    finally:
        cap.release()
    # 可変フレームレートの疑い: r_frame_rate と avg_frame_rate の乖離
    r, a = info.get("r_frame_rate") or 0, info.get("avg_frame_rate") or 0
    info["vfr_suspected"] = bool(r and a and abs(r - a) / max(r, a) > 0.02)
    return info


def iter_frames(video_path: str, sample_fps: float, start_s: float = 0.0, end_s: float | None = None) -> Iterator[tuple[int, float, np.ndarray]]:
    """実タイムスタンプ（コンテナの pts）に基づき sample_fps 間隔でフレームを返す。
    返り値: (サンプル番号, 時刻 秒, BGR 画像)。可変フレームレートでも時刻がずれない。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("動画を開けません")
    dt = 1.0 / sample_fps
    next_t = start_s
    k = 0
    last_t = -1.0
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t <= last_t:  # 一部コンテナで pts が取れない場合はフレーム番号から推定
                fps = cap.get(cv2.CAP_PROP_FPS) or sample_fps
                t = last_t + 1.0 / fps
            last_t = t
            if end_s is not None and t > end_s + 1e-6:
                break
            if t + 1e-6 >= next_t:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                yield k, t, frame
                k += 1
                # 次のサンプル時刻（元の fps より細かい指定なら同じフレームは返さない）
                next_t += dt
                while next_t < t - 1e-6:
                    next_t += dt
    finally:
        cap.release()


class DecodeStage:
    name = "decode"

    def run(self, ctx, data):
        info = probe(ctx.video_path)
        fps = float(ctx.params.get("fps") or 30)
        start = float(ctx.params.get("start_s") or 0)
        end = ctx.params.get("end_s")
        ctx.scratch["sample_fps"] = fps
        ctx.scratch["range"] = (start, float(end) if end is not None else None)
        n_est = int(((float(end) if end is not None else info.get("duration", 0)) - start) * fps)
        return {"video": info, "sample_fps": fps, "start_s": start, "end_s": end, "estimated_samples": max(0, n_est),
                "summary": {"duration": info.get("duration"), "size": [info.get("width"), info.get("height")], "vfr_suspected": info.get("vfr_suspected")}}
