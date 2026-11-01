"""コマごとの処理（ストリーミング）: 対象選手の検出・追跡 → 姿勢推定 → 板検出 → カメラ動作。
フレーム画像はメモリに残さず、各段階の出力（座標・信頼度）だけを配列に保存する。
出力は段階別に分けて保存するので、どの段階で誤差が出たか追跡できる。"""
from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from .decode import iter_frames
from .pose import make_backend
from .ski import detect_skis

CORE = [11, 12, 23, 24, 25, 26, 27, 28]
BONE_CHECK = [(11, 13), (12, 14), (11, 23), (12, 24), (23, 25), (24, 26), (25, 27), (26, 28)]


def bbox_of(kp: list[list[float]]) -> tuple[float, float, float, float]:
    pts = [(p[0], p[1]) for p in kp if p[2] >= 0.3]
    if not pts:
        return 0.5, 0.5, 1.0, 1.0
    xs, ys = zip(*pts)
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)


def good_pose(kp) -> bool:
    return sum(kp[i][2] for i in CORE) / len(CORE) > 0.35


def bone_lens(world) -> list[float]:
    return [math.dist(world[a], world[b]) for a, b in BONE_CHECK]


class Tracker:
    """対象選手の追跡: 前コマの骨格 bbox の周りを正方形に切り出して拡大し、そこで姿勢推定する。
    見失ったら探索範囲を広げ、タイル探索に戻る。体格に比べて飛びすぎた検出・骨の長さが合わない検出は別人として捨てる。"""

    def __init__(self, backend, vw: int, vh: int, target: tuple[float, float] | None, sample_fps: float):
        self.b = backend; self.vw = vw; self.vh = vh; self.fps = sample_fps
        self.target = target
        self.roi = (target[0] * vw, target[1] * vh, max(vh * 0.5, 256)) if target else None
        self.prev_center = None; self.lost = 0; self.last_good = None; self.last_good_i = -1; self.last_size = 0.0
        self.bone_hist: list[list[float]] = []

    def _detect_in(self, bgr, roi):
        if roi is None:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            r = self.b.detect(rgb)
            return (r, None) if r else (None, None)
        cx, cy, size = roi
        size = min(size, self.vw, self.vh)
        x0 = int(max(0, min(self.vw - size, cx - size / 2))); y0 = int(max(0, min(self.vh - size, cy - size / 2)))
        s = int(size)
        crop = bgr[y0:y0 + s, x0:x0 + s]
        if crop.size == 0:
            return None, None
        crop = cv2.resize(crop, (512, 512))
        r = self.b.detect(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not r:
            return None, None
        r["kp"] = [[(x0 + p[0] * s) / self.vw, (y0 + p[1] * s) / self.vh, p[2]] for p in r["kp"]]
        return r, (x0, y0, s)

    def _grid(self, bgr, near, last_size):
        m = min(self.vw, self.vh)
        scales = [last_size * 2.2, last_size * 1.5, last_size * 3.5] if last_size else ([0.5, 0.3, 0.18] if near else [0.5, 0.3])
        if not last_size:
            scales = [x * m for x in scales]
        best, best_score = None, -1e9
        for sz in scales:
            size = max(min(sz, m), 128); step = size * 0.6
            tiles = []
            y = size / 2
            while y < self.vh + step / 2:
                x = size / 2
                while x < self.vw + step / 2:
                    tiles.append((min(x, self.vw - size / 2), min(y, self.vh - size / 2), size)); x += step
                y += step
            if near:
                nx, ny = near[0] * self.vw, near[1] * self.vh
                tiles.sort(key=lambda t: math.hypot(t[0] - nx, t[1] - ny)); tiles = tiles[:6]
            for t in tiles:
                r, _ = self._detect_in(bgr, t)
                if not r or not good_pose(r["kp"]):
                    continue
                cx, cy, _, _ = bbox_of(r["kp"])
                sc = sum(r["kp"][k][2] for k in CORE) / len(CORE)
                if near:
                    sc -= math.hypot(cx - near[0], cy - near[1]) * 1.5
                if sc > best_score:
                    best, best_score = r, sc
            if best and near:
                break
        return best

    def step(self, i: int, bgr) -> dict[str, Any]:
        """1 コマ処理。戻り値: {"pose": r|None, "roi": (x0,y0,s)|None, "search": 'roi'|'full'|'grid'|None, "reject": reason|None}"""
        out: dict[str, Any] = {"pose": None, "roi": None, "search": None, "reject": None}
        r, used = (self._detect_in(bgr, self.roi) if self.roi else (None, None))
        search = "roi" if r else None
        if not r or not good_pose(r["kp"]):
            r, used = self._detect_in(bgr, None); search = "full" if r and good_pose(r["kp"]) else None
            if r and not good_pose(r["kp"]):
                r = None
        if not r and (i == 0 or ((self.prev_center or self.target) and self.lost % 3 == 2) or (not self.prev_center and not self.target and self.lost % 6 == 5)):
            near = (self.prev_center[0] / self.vw, self.prev_center[1] / self.vh) if self.prev_center else (None if self.last_good else self.target)
            r = self._grid(bgr, near, self.last_size); search = "grid" if r else None; used = None
        if r and self.last_good:
            gap = i - self.last_good_i
            if gap <= self.fps:
                cx, cy, _, _ = bbox_of(r["kp"]); pcx, pcy, pw, ph = bbox_of(self.last_good)
                body = max(pw, ph, 0.05)
                if math.hypot(cx - pcx, cy - pcy) > body * (0.6 + 0.4 * gap):
                    out["reject"] = "jump"; r = None
        if r and r.get("world") and len(self.bone_hist) >= 8:
            L = bone_lens(r["world"]); bad = 0
            for k, v in enumerate(L):
                col = sorted(h[k] for h in self.bone_hist); med = col[len(col) // 2]
                if med > 0 and abs(v - med) / med > 0.35:
                    bad += 1
            if bad >= 2:
                out["reject"] = "bone_length"; r = None
        if r:
            if r.get("world"):
                self.bone_hist.append(bone_lens(r["world"])); self.bone_hist = self.bone_hist[-45:]
            cx, cy, w, h = bbox_of(r["kp"])
            size = max(w * self.vw, h * self.vh) * 1.6
            px, py = cx * self.vw, cy * self.vh
            if self.prev_center:
                g = max(1, i - self.last_good_i)
                px += (px - self.prev_center[0]) / g * 0.7; py += (py - self.prev_center[1]) / g * 0.7
            self.prev_center = (cx * self.vw, cy * self.vh)
            self.roi = (px, py, max(size, 128)); self.lost = 0; self.last_good = r["kp"]; self.last_good_i = i
            self.last_size = max(w * self.vw, h * self.vh)
            out.update(pose=r, roi=used, search=search)
        else:
            self.lost += 1
            if self.roi and self.lost >= 2:
                self.roi = (self.roi[0], self.roi[1], self.roi[2] * 1.6)
            if self.lost >= 6:
                self.roi = None
        return out


def camera_shift(prev_gray, gray, mask) -> tuple[float, float, float]:
    """背景（人物を除いた領域）の位相相関で画面全体の移動量（px、縮小画像基準を元の倍率に戻す）と応答値を返す。"""
    if prev_gray is None:
        return 0.0, 0.0, 0.0
    a = prev_gray.astype(np.float32) * mask; b = gray.astype(np.float32) * mask
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(a, b, win)
    return float(dx), float(dy), float(resp)


class PerFrameStage:
    name = "perframe"

    def run(self, ctx, data):
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        fps = ctx.scratch["sample_fps"]; start, end = ctx.scratch["range"]
        p = ctx.params
        backend = make_backend(p.get("pose_backend", "mediapipe"), ctx.model_dir, variant=p.get("pose_model", "heavy"), min_conf=float(p.get("sensitivity", 0.3)))
        ctx.model_versions["pose"] = backend.version
        ctx.model_versions["ski_detector"] = "classical_edge_v2"
        target = tuple(p["target"]) if p.get("target") else None
        tracker = Tracker(backend, vw, vh, target, fps)
        est_total = max(1, data["decode"]["estimated_samples"])
        frames, dets, skis, cam = [], [], [], []
        prev_small = None; scale = 160 / max(vw, vh)
        cam_x = cam_y = 0.0
        try:
            for i, t, bgr in iter_frames(ctx.video_path, fps, start, end):
                ctx.check_cancel()
                step = tracker.step(i, bgr)
                r = step["pose"]
                # カメラ動作: 人物 bbox を除いた縮小グレー画像の位相相関
                small = cv2.cvtColor(cv2.resize(bgr, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
                mask = np.ones_like(small, dtype=np.float32)
                if r:
                    cx, cy, w, h = bbox_of(r["kp"])
                    x0 = int(max(0, (cx - w * 0.7) * small.shape[1])); x1 = int(min(small.shape[1], (cx + w * 0.7) * small.shape[1]))
                    y0 = int(max(0, (cy - h * 0.7) * small.shape[0])); y1 = int(min(small.shape[0], (cy + h * 0.7) * small.shape[0]))
                    mask[y0:y1, x0:x1] = 0
                dx, dy, resp = camera_shift(prev_small, small, mask)
                prev_small = small
                cam_x += dx / scale; cam_y += dy / scale
                cam.append({"i": i, "dx": dx / scale, "dy": dy / scale, "cum_x": cam_x, "cum_y": cam_y, "resp": resp})
                ski = None
                if r:
                    try:
                        ski = detect_skis(bgr, r["kp"], vw, vh)
                    except Exception:
                        ski = None
                frames.append({"i": i, "t": round(t, 4), "kp": r["kp"] if r else None, "world": r.get("world") if r else None, "src": "det" if r else None})
                dets.append({"i": i, "search": step["search"], "roi": step["roi"], "reject": step["reject"]})
                skis.append({"i": i, "ski": ski})
                if i % 5 == 0:
                    ctx.progress(0.05 + 0.75 * min(1.0, (i + 1) / est_total), self.name, f"コマ {i + 1} / 約{est_total}")
        finally:
            backend.close()
        n_det = sum(1 for f in frames if f["kp"])
        return {"frames": frames, "detection": dets, "ski": skis, "camera": cam, "keypoint_format": backend.keypoint_format,
                "summary": {"samples": len(frames), "detected": n_det, "detect_rate": round(n_det / max(1, len(frames)), 3),
                            "rejects": {k: sum(1 for d in dets if d["reject"] == k) for k in ("jump", "bone_length")},
                            "ski_detected_L": sum(1 for s in skis if s["ski"] and s["ski"]["L"] and s["ski"]["L"]["conf"] >= 0.55),
                            "ski_detected_R": sum(1 for s in skis if s["ski"] and s["ski"]["R"] and s["ski"]["R"]["conf"] >= 0.55)}}
