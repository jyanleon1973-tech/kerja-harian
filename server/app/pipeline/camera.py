"""撮影方向の判定とカメラ動作を差し引いた選手の軌跡。
- 撮影方向: 肩幅 / 体幹長（側面で小さい）と顔の可視度（正面か背面か）。ユーザー指定があれば優先。
- 軌跡: 腰中点の画像位置からカメラの累積移動（位相相関）を差し引く。ズームは補正しない（信頼度に反映）。"""
from __future__ import annotations

from typing import Any


def _median(a):
    if not a:
        return 0.0
    s = sorted(a); return s[len(s) // 2]


def estimate_view(frames: list[dict[str, Any]], vw: int, vh: int) -> dict[str, Any]:
    rs, face = [], []
    for f in frames:
        kp = f.get("kp")
        if not kp or f.get("src") != "det":
            continue
        sw = ((kp[11][0] - kp[12][0]) * vw) ** 2 + ((kp[11][1] - kp[12][1]) * vh) ** 2
        smx, smy = (kp[11][0] + kp[12][0]) / 2 * vw, (kp[11][1] + kp[12][1]) / 2 * vh
        hmx, hmy = (kp[23][0] + kp[24][0]) / 2 * vw, (kp[23][1] + kp[24][1]) / 2 * vh
        torso = ((smx - hmx) ** 2 + (smy - hmy) ** 2) ** 0.5
        if torso > 2:
            rs.append(sw ** 0.5 / torso)
        face.append((kp[0][2] + kp[2][2] + kp[5][2]) / 3)
    r, fv = _median(rs), _median(face)
    facing = "toward" if fv > 0.6 else "away"
    auto = "unknown" if not rs else ("side" if r < 0.42 else ("front" if facing == "toward" else "back") if r > 0.72 else "oblique")
    return {"auto": auto, "facing": facing, "ratio": round(r, 3), "n": len(rs)}


class CameraStage:
    name = "camera"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        est = estimate_view(frames, vw, vh)
        sel = ctx.params.get("view", "auto")
        view = est["auto"] if sel in (None, "auto") else sel
        cam = data["perframe"]["camera"]
        # カメラ動作の大きさ（総移動量 / 画面幅）と、位相相関の応答が低いコマの割合
        total_shift = sum(abs(c["dx"]) + abs(c["dy"]) for c in cam) / max(1, vw)
        low_resp = sum(1 for c in cam if c["resp"] < 0.05) / max(1, len(cam))
        camera_moving = total_shift > 0.5  # 画面幅の半分以上パンしている
        traj = []
        for f, c in zip(frames, cam):
            kp = f.get("kpS")
            if not kp:
                traj.append(None); continue
            hx, hy = (kp[23][0] + kp[24][0]) / 2 * vw, (kp[23][1] + kp[24][1]) / 2 * vh
            traj.append({"x": hx + c["cum_x"], "y": hy + c["cum_y"], "img_x": hx, "img_y": hy})
        ctx.scratch["view"] = view; ctx.scratch["traj"] = traj
        return {"view": view, "view_auto": est, "selected": sel, "camera_moving": camera_moving, "total_shift_ratio": round(total_shift, 3),
                "low_response_ratio": round(low_resp, 3), "trajectory": traj,
                "summary": {"view": view, "auto": est["auto"], "camera_moving": camera_moving}}
