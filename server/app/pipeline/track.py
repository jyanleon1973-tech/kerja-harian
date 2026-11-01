"""選手の追跡データ（AI 側の出力）と、追尾カメラの軌道（カメラ制御側の出力）。両者は分離する。

AI 側（TrackStage）: コマごとに 選手 ID、人物の外接領域、身体中心、板・ブーツを含む領域、追跡信頼度、状態（det / interp / lost）。
カメラ側（plan_camera）: 設定（モード・表示サイズ・滑らかさ・中心位置・拡大率）から、切り抜き中心・幅・高さ・ズーム倍率を
  動画全体を見て（前後参照の One Euro）計算し、急な移動・ズーム変化を抑える。見失ったら最後の位置を短時間保持し、
  その後は全体表示へ戻す。座標はすべて元動画の正規化座標（0-1）。表示・書き出し側はこの切り抜きを適用するだけで、解析データは変更しない。"""
from __future__ import annotations

import math
from typing import Any

from .temporal import one_euro_series

MAX_ZOOM = 4.0
MIN_SRC_WIDTH_PX = 640   # 切り抜き幅がこれを下回ると「元動画の解像度が不足」


def track_frame(f: dict[str, Any], vw: int, vh: int) -> dict[str, Any] | None:
    kp = f.get("kpS"); q = f.get("q")
    if not kp or not q:
        return None
    pts = [(p[0], p[1]) for j, p in enumerate(kp) if q[j] >= 0.3]
    if len(pts) < 4:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    body = [min(xs), min(ys), max(xs), max(ys)]
    hip = ((kp[23][0] + kp[24][0]) / 2, (kp[23][1] + kp[24][1]) / 2)
    upper = [min(kp[j][0] for j in (0, 7, 8, 11, 12, 13, 14, 23, 24)), min(kp[j][1] for j in (0, 7, 8, 11, 12)), max(kp[j][0] for j in (0, 7, 8, 11, 12, 13, 14, 23, 24)), max(kp[23][1], kp[24][1])]
    feet = [min(kp[j][0] for j in range(27, 33)), min(kp[j][1] for j in range(25, 33)), max(kp[j][0] for j in range(27, 33)), max(kp[j][1] for j in range(27, 33))]
    full = list(body); skis = list(feet)
    sk = f.get("ski") or {}
    for key in ("L", "R"):
        s = sk.get(key)
        if not s or s.get("conf", 0) < 0.55:
            continue
        dx, dy = math.cos(s["ang"]), math.sin(s["ang"])
        for t in (-s["tail"], s["tip"]):
            x = (s["fx"] + dx * t) / vw; y = (s["fy"] + dy * t) / vh
            full[0] = min(full[0], x); full[1] = min(full[1], y); full[2] = max(full[2], x); full[3] = max(full[3], y)
            skis[0] = min(skis[0], x); skis[1] = min(skis[1], y); skis[2] = max(skis[2], x); skis[3] = max(skis[3], y)
    # ストックは検出していないので、手首の先に少し余白を足す
    for j in (15, 16):
        if q[j] >= 0.3:
            full[0] = min(full[0], kp[j][0] - 0.02); full[2] = max(full[2], kp[j][0] + 0.02)
    qcore = min(q[j] for j in (11, 12, 23, 24, 25, 26, 27, 28))
    return {"track_id": 1, "body": [round(v, 4) for v in body], "full": [round(v, 4) for v in full], "upper": [round(v, 4) for v in upper], "skis": [round(v, 4) for v in skis],
            "center": [round(hip[0], 4), round(hip[1], 4)], "conf": round(qcore * (0.7 if f.get("src") == "interp" else 1.0), 3), "state": f.get("src") or "lost"}


def plan_camera(tracks: list[dict[str, Any] | None], dt: float, vw: int, vh: int, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """追尾カメラの軌道。settings: mode(normal|follow|zoom|skis), framing(full|body|upper|skis), target_frac(0.5-0.95), zoom_mult(0.5-2),
    smooth(0-1), center_y(-0.3..0.3), max_zoom. 出力: 各コマ {cx, cy, w, h, zoom, state, lowres}（正規化座標）。"""
    s = {"mode": "zoom", "framing": "full", "target_frac": 0.75, "zoom_mult": 1.0, "smooth": 0.5, "center_y": 0.0, "max_zoom": MAX_ZOOM}
    s.update({k: v for k, v in (settings or {}).items() if v is not None})
    n = len(tracks); aspect = vw / vh
    if s["mode"] == "normal":
        return [{"cx": 0.5, "cy": 0.5, "w": 1.0, "h": 1.0, "zoom": 1.0, "state": "normal", "lowres": False} for _ in range(n)]
    framing = "skis" if s["mode"] == "skis" else s["framing"]
    key = {"full": "full", "body": "body", "upper": "upper", "skis": "skis"}[framing]
    # 目標の中心とズーム（コマごと）
    cxs, cys, zs, states = [], [], [], []
    for t in tracks:
        if not t or t["conf"] < 0.2:
            cxs.append(None); cys.append(None); zs.append(None); states.append("lost"); continue
        box = t[key]
        cx = (box[0] + box[2]) / 2; cy = (box[1] + box[3]) / 2 + s["center_y"] * (box[3] - box[1])
        if s["mode"] == "follow":
            z = 1.0 * s["zoom_mult"]
        else:
            bh = max(1e-3, (box[3] - box[1]) * 1.15)                       # 余白 15%
            bw = max(1e-3, (box[2] - box[0]) * 1.15) / aspect             # 幅を高さの単位に換算
            z = s["target_frac"] / max(bh, bw) * s["zoom_mult"]
        z = max(1.0, min(s["max_zoom"], z))
        cxs.append(cx); cys.append(cy); zs.append(z); states.append(t["state"])
    # 平滑化（前後参照）。smooth が大きいほどカットオフを下げる
    minc = 0.3 + (1 - s["smooth"]) * 2.2
    sx = one_euro_series(cxs, dt, minc, 0.8); sy = one_euro_series(cys, dt, minc, 0.8); sz = one_euro_series(zs, dt, minc * 0.7, 0.3)
    out = []
    hold_frames = max(1, round(1.0 / dt)); lost_run = 0; last = None
    max_pan = 0.6 * dt; max_zoom_rate = 1.5 * dt      # 画面幅/秒、倍率/秒
    for i in range(n):
        if sx[i] is None:
            lost_run += 1
            if last and lost_run <= hold_frames:
                cur = dict(last, state="hold")
            else:
                # 全体表示へ徐々に戻す
                if last:
                    cur = {"cx": last["cx"] + (0.5 - last["cx"]) * 0.1, "cy": last["cy"] + (0.5 - last["cy"]) * 0.1, "zoom": last["zoom"] + (1.0 - last["zoom"]) * 0.1, "state": "lost"}
                else:
                    cur = {"cx": 0.5, "cy": 0.5, "zoom": 1.0, "state": "lost"}
        else:
            lost_run = 0
            cur = {"cx": sx[i], "cy": sy[i], "zoom": sz[i], "state": "tracking" if states[i] == "det" else "interp"}
            if last:   # 急な移動・ズーム変化の抑制
                cur["cx"] = last["cx"] + max(-max_pan, min(max_pan, cur["cx"] - last["cx"]))
                cur["cy"] = last["cy"] + max(-max_pan, min(max_pan, cur["cy"] - last["cy"]))
                cur["zoom"] = last["zoom"] + max(-max_zoom_rate, min(max_zoom_rate, cur["zoom"] - last["zoom"]))
        z = max(1.0, min(s["max_zoom"], cur["zoom"]))
        w, h = 1.0 / z, 1.0 / z
        cx = min(1 - w / 2, max(w / 2, cur["cx"])); cy = min(1 - h / 2, max(h / 2, cur["cy"]))
        rec = {"cx": round(cx, 4), "cy": round(cy, 4), "w": round(w, 4), "h": round(h, 4), "zoom": round(z, 3), "state": cur["state"], "lowres": bool(w * vw < MIN_SRC_WIDTH_PX)}
        out.append(rec); last = {"cx": cx, "cy": cy, "zoom": z}
    return out


class TrackStage:
    name = "track"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        tr = [track_frame(f, vw, vh) for f in frames]
        ctx.scratch["tracks"] = tr
        dt = 1 / ctx.scratch["sample_fps"]
        default_cam = plan_camera(tr, dt, vw, vh, {"mode": "zoom", "framing": "full"})
        ctx.scratch["camera_default"] = default_cam
        n = max(1, len(tr))
        return {"tracks": tr, "camera_default": default_cam, "settings_default": {"mode": "zoom", "framing": "full", "target_frac": 0.75, "zoom_mult": 1.0, "smooth": 0.5, "center_y": 0.0, "max_zoom": MAX_ZOOM},
                "summary": {"tracked": sum(1 for t in tr if t), "tracked_rate": round(sum(1 for t in tr if t) / n, 3), "lost_frames": sum(1 for c in default_cam if c["state"] == "lost"),
                            "lowres_frames": sum(1 for c in default_cam if c["lowres"]), "mean_zoom": round(sum(c["zoom"] for c in default_cam) / n, 2)}}
