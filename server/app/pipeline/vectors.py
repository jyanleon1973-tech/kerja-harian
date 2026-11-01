"""運動ベクトルと身体運動指標。
モード A: 推定重心の移動ベクトル（画像上、カメラの平行移動を差し引く）。観測に基づく推定値。
モード B: 左右スキーの「荷重傾向スコア」の枠組み。入力は身体運動指標のみで、センサー正解との検証が済んでいないため
          validated=false を付け、表示側は灰色の参考表示に限定する。% や N は出さない。
モード C: 接触反力。3D 復元・雪面校正・質量がないため計算しない（available=false）。"""
from __future__ import annotations

import math
from typing import Any

from .temporal import one_euro_series


def _conf_core(f):
    q = f.get("q")
    if not q:
        return 0.0
    c = min(q[j] for j in (11, 12, 23, 24, 25, 26, 27, 28))
    return c * (0.7 if f.get("src") == "interp" else 1.0)


class VectorStage:
    name = "vectors"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]; metrics = ctx.scratch["metrics"]; turn = ctx.scratch["turn"]; phase = ctx.scratch["phase"]
        cam = data["perframe"]["camera"]; view = ctx.scratch["view"]
        fps = ctx.scratch["sample_fps"]; dt = 1 / fps; n = len(frames)
        camera_moving = data["camera"]["camera_moving"]
        # 推定重心（px）にカメラ累積移動を足してコース座標に近づける（平行移動のみ。ズームは未補正）
        cx = [m["cog2"][0] + cam[i]["cum_x"] if m else None for i, m in enumerate(metrics)]
        cy = [m["cog2"][1] + cam[i]["cum_y"] if m else None for i, m in enumerate(metrics)]
        sx = one_euro_series(cx, dt, 1.5, 0.5); sy = one_euro_series(cy, dt, 1.5, 0.5)
        k = max(1, round(0.08 / dt))
        vectors, indicators = [], []
        for i in range(n):
            m = metrics[i]; f = frames[i]
            if not m or sx[i] is None:
                vectors.append(None); indicators.append(None); continue
            a = max(0, i - k); b = min(n - 1, i + k)
            if sx[a] is None or sx[b] is None or b == a:
                vectors.append(None); indicators.append(None); continue
            vx = (sx[b] - sx[a]) / ((b - a) * dt); vy = (sy[b] - sy[a]) / ((b - a) * dt)   # px/s
            BH = m["BH"]
            mag = math.hypot(vx, vy) / BH                                              # 身長比/秒
            conf = _conf_core(f) * (0.75 if cam[i]["resp"] < 0.05 else 1.0) * (0.8 if camera_moving else 1.0)
            vectors.append({"mode": "A", "quantity": "cog_motion_image", "dx": round(vx, 2), "dy": round(vy, 2), "mag_bh_s": round(mag, 3),
                            "dir_deg": round(math.degrees(math.atan2(vy, vx)), 1), "conf": round(conf, 3), "camera_compensated": True, "apparent_only": camera_moving,
                            "label": "重心移動（推定・画像上、カメラ平行移動を補正）"})
            M = m["M"]
            t = turn[i] or 0
            out_key, in_key = ("kneeL", "kneeR") if t > 0 else ("kneeR", "kneeL") if t < 0 else (None, None)
            knee_out = M[out_key]["v"] if out_key and M[out_key]["v"] is not None else None
            knee_in = M[in_key]["v"] if in_key and M[in_key]["v"] is not None else None
            # 推定重心と左右足首の横方向距離（身長比 %）: 正面・背面・斜めで意味を持つ
            kp = f["kpS"]; vw_bh = BH
            dxl = (m["cog2"][0] - kp[27][0] * data["decode"]["video"]["width"]) / vw_bh * 100
            dxr = (m["cog2"][0] - kp[28][0] * data["decode"]["video"]["width"]) / vw_bh * 100
            indicators.append({
                "turn": t, "phase": phase[i], "knee_out": knee_out, "knee_in": knee_in,
                "cog_to_ankleL_pct": round(dxl, 2) if view != "side" else None, "cog_to_ankleR_pct": round(dxr, 2) if view != "side" else None,
                "cog_speed_bh_s": round(mag, 3), "hip_height_pct": M["hipHeight"]["v"], "cog_fwd_pct": M["cogFwd"]["v"], "cog_lat_pct": M["cogLat"]["v"],
                "ski_open_deg": M["skiOpen"]["v"], "note": "身体運動指標。荷重ではない",
            })
        # 脚の伸展速度（膝屈曲の時間微分、deg/s）
        for key in ("knee_out", "knee_in"):
            series = [ind[key] if ind and ind.get(key) is not None else None for ind in indicators]
            for i, ind in enumerate(indicators):
                if not ind:
                    continue
                a = max(0, i - k); b = min(n - 1, i + k)
                ind[key + "_rate"] = round((series[b] - series[a]) / ((b - a) * dt), 1) if series[a] is not None and series[b] is not None and b > a else None
        # モード B の枠組み（未検証）: 正面・背面・斜めで、重心が外脚側・内脚側のどちらに寄っているかの相対スコア。% ではなく 0-1 の傾向。
        tendency = []
        for i, ind in enumerate(indicators):
            if not ind or ind.get("cog_to_ankleL_pct") is None:
                tendency.append(None); continue
            dl, dr = abs(ind["cog_to_ankleL_pct"]), abs(ind["cog_to_ankleR_pct"])
            s = dl + dr
            # 重心が近い側の足ほど傾向スコアを高くする（単純な近接モデル。検証前）
            tL = 1 - dl / s if s > 1e-6 else 0.5; tR = 1 - tL
            conf = _conf_core(frames[i]) * 0.5   # 未検証モデルなので信頼度の上限を半分にする
            tendency.append({"mode": "B", "L": round(tL, 3), "R": round(tR, 3), "conf": round(conf, 3), "validated": False, "unit": "relative(0-1)", "label": "荷重傾向（参考・未検証）"})
        return {"vectors": vectors, "indicators": indicators, "tendency": tendency,
                "modes": {"A": {"available": True, "status": "observed_image_motion", "note": "推定重心の画像上の移動。カメラの平行移動は補正、ズームは未補正"},
                          "B": {"available": True, "status": "reference_only_unvalidated", "note": "センサー正解との検証が済むまで灰色の参考表示のみ"},
                          "C": {"available": False, "status": "disabled", "note": "3D 復元・雪面校正・質量情報・力学モデルが未整備"}},
                "summary": {"frames_with_vector": sum(1 for v in vectors if v), "mean_cog_speed_bh_s": round(sum(v["mag_bh_s"] for v in vectors if v) / max(1, sum(1 for v in vectors if v)), 3)}}
