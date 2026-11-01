"""解析結果を焼き込んだ動画の生成（OpenCV で描画、FFmpeg で H.264 エンコード）。
不確実な関節は白抜き・点線、板は検出できたコマだけ実測長で描く。"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

import cv2
import numpy as np

from .decode import iter_frames

CONN = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (24, 26), (26, 28), (27, 29), (29, 31), (27, 31), (28, 30), (30, 32), (28, 32)]
QMIN = 0.5
COL_L, COL_R, COL_COG, COL_FEET = (11, 158, 245), (248, 189, 56), (68, 68, 239), (94, 197, 34)


def _dashed(img, a, b, color, thick):
    n = max(1, int(np.hypot(b[0] - a[0], b[1] - a[1]) / 8))
    for k in range(0, n, 2):
        p = (int(a[0] + (b[0] - a[0]) * k / n), int(a[1] + (b[1] - a[1]) * k / n)); q = (int(a[0] + (b[0] - a[0]) * (k + 1) / n), int(a[1] + (b[1] - a[1]) * (k + 1) / n))
        cv2.line(img, p, q, color, thick, cv2.LINE_AA)


def draw_overlay(img: np.ndarray, frame: dict[str, Any], metric: dict[str, Any] | None, view: str, turn, phase, opts: dict[str, Any]) -> None:
    h, w = img.shape[:2]
    kp = frame.get("kpS"); q = frame.get("q")
    unit = max(1.0, w / 640)
    if kp and q:
        P = [(int(p[0] * w), int(p[1] * h)) for p in kp]
        ys = [p[1] for p in kp if p[2] >= 0.3]; k = max(0.3, min(1.0, ((max(ys) - min(ys)) * h if ys else h * 0.5) / (320 * unit)))
        sure = lambda j: q[j] >= QMIN
        if opts.get("skel", True):
            for a, b in CONN:
                ok = sure(a) and sure(b)
                if not ok and not opts.get("unsure", True):
                    continue
                col = COL_L if a % 2 == 1 else COL_R
                if ok:
                    cv2.line(img, P[a], P[b], col, max(1, int(3 * unit * k)), cv2.LINE_AA)
                else:
                    _dashed(img, P[a], P[b], col, max(1, int(1.5 * unit * k)))
            for j in range(11, len(P)):
                if sure(j):
                    cv2.circle(img, P[j], max(2, int(3.5 * unit * k)), (255, 255, 255), -1, cv2.LINE_AA)
                elif opts.get("unsure", True):
                    cv2.circle(img, P[j], max(2, int(3.5 * unit * k)), (200, 200, 200), 1, cv2.LINE_AA)
        if opts.get("lines", True):
            for a, b in ((11, 12), (23, 24)):
                if sure(a) and sure(b):
                    cv2.line(img, P[a], P[b], (240, 240, 240), max(1, int(4.5 * unit * k)), cv2.LINE_AA)
        if opts.get("ski", True) and frame.get("ski"):
            for key in ("L", "R"):
                s = frame["ski"].get(key)
                if not s or s["conf"] < 0.55 or (key == "R" and frame["ski"].get("shared")):
                    continue
                dx, dy = np.cos(s["ang"]), np.sin(s["ang"])
                a = (int(s["fx"] - dx * s["tail"]), int(s["fy"] - dy * s["tail"])); b = (int(s["fx"] + dx * s["tip"]), int(s["fy"] + dy * s["tip"]))
                cv2.line(img, a, b, (255, 255, 255) if frame["ski"].get("shared") else (COL_L if key == "L" else COL_R), max(2, int((3 + 3 * s["conf"]) * unit * k)), cv2.LINE_AA)
        if opts.get("cog", True) and metric:
            c = (int(metric["cog2"][0]), int(metric["cog2"][1]))
            cv2.circle(img, c, max(3, int(7 * unit * k)), COL_COG, -1, cv2.LINE_AA)
            _dashed(img, c, (c[0], h), COL_COG, max(1, int(2 * unit * k)))
            fc = (int(metric["feet2"][0]), int(metric["feet2"][1]))
            cv2.circle(img, fc, max(3, int(6 * unit * k)), COL_FEET, max(1, int(2 * unit * k)), cv2.LINE_AA)
    if opts.get("text", True):
        lines = [f"{frame['t']:.2f}s  {view}  " + ("L-turn" if turn == -1 else "R-turn" if turn == 1 else "straight" if turn == 0 else "unknown") + (f" {['early', 'mid', 'late'][phase]}" if phase is not None else "")]
        if metric:
            show = ["trunkFwd", "shinL", "shinR", "kneeL", "kneeR", "cogFwd"] if view == "side" else ["shoulderTilt", "pelvisTilt", "lean", "angulation", "stance", "skiOpen", "cogLat"]
            for key in show:
                r = metric["M"].get(key)
                if not r or r["cls"] == "na":
                    continue
                lines.append(f"{key}{'*' if r['cls'] == 'est' else ''}: " + ("n/a(low conf)" if r["v"] is None else f"{r['v']:+.0f}"))
        fs = 0.45 * unit; lh = int(18 * unit)
        box_w = int(max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)[0][0] for s in lines) + 16 * unit)
        ov = img.copy(); cv2.rectangle(ov, (6, 6), (6 + box_w, 10 + lh * len(lines)), (30, 23, 15), -1)
        cv2.addWeighted(ov, 0.7, img, 0.3, 0, img)
        for n, s in enumerate(lines):
            cv2.putText(img, s, (int(12 * unit), int(10 + lh * (n + 0.8))), cv2.FONT_HERSHEY_SIMPLEX, fs, (235, 235, 235), 1, cv2.LINE_AA)


def render_video(video_path: str, out_path: str, frames: list[dict[str, Any]], metrics: list, view: str, turn: list, phase: list, sample_fps: float, start_s: float, end_s: float | None, speed: float = 1.0, opts: dict[str, Any] | None = None, max_w: int = 1920) -> dict[str, Any]:
    opts = opts or {}
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg が見つかりません")
    proc = None; n = 0; size = None
    idx_by_i = {f["i"]: k for k, f in enumerate(frames)}
    out_fps = max(1.0, sample_fps * max(0.05, min(1.0, speed)))
    for i, t, bgr in iter_frames(video_path, sample_fps, start_s, end_s):
        k = idx_by_i.get(i)
        if k is None:
            continue
        h, w = bgr.shape[:2]
        if w > max_w:
            sc = max_w / w; bgr = cv2.resize(bgr, (max_w, int(h * sc)))
        if size is None:
            size = (bgr.shape[1] // 2 * 2, bgr.shape[0] // 2 * 2)
            proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}", "-r", f"{out_fps}", "-i", "-",
                                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
        bgr = cv2.resize(bgr, size)
        # 描画座標は元解像度基準（kpS は正規化、ski/cog2 は px）→ 縮小率を掛ける
        sx = size[0] / w if w else 1.0
        fr = frames[k]; m = metrics[k] if k < len(metrics) else None
        if m:
            m = {**m, "cog2": [m["cog2"][0] * sx, m["cog2"][1] * sx], "feet2": [m["feet2"][0] * sx, m["feet2"][1] * sx]}
        if fr.get("ski"):
            fr = {**fr, "ski": {kk: ({**v, "fx": v["fx"] * sx, "fy": v["fy"] * sx, "tip": v["tip"] * sx, "tail": v["tail"] * sx} if isinstance(v, dict) else v) for kk, v in fr["ski"].items()}}
        draw_overlay(bgr, fr, m, view, turn[k] if k < len(turn) else None, phase[k] if k < len(phase) else None, opts)
        proc.stdin.write(bgr.tobytes()); n += 1
    if proc:
        proc.stdin.close(); proc.wait(timeout=600)
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg のエンコードに失敗しました")
    return {"frames": n, "fps": out_fps, "size": size}
