"""時系列補正: 左右の取り違え修正、1 コマだけの外れ値補修、短い欠落の補間（フラグ付き）、One Euro 平滑化（前後方向平均）。
急な動きを消さないよう、速度が大きいほど平滑化を弱める。補間した区間は src='interp' とし、確からしさを下げる。"""
from __future__ import annotations

import math
from typing import Any

LEGS_L = [23, 25, 27, 29, 31]; LEGS_R = [24, 26, 28, 30, 32]
ARMS_L = [11, 13, 15, 17, 19, 21]; ARMS_R = [12, 14, 16, 18, 20, 22]


def _bbox_h(kp) -> float:
    ys = [p[1] for p in kp if p[2] >= 0.3]
    return (max(ys) - min(ys)) if ys else 0.3


def fix_left_right(frames: list[dict[str, Any]], skis: list[dict[str, Any]]) -> int:
    prev = None; swaps = 0
    for f, s in zip(frames, skis):
        if not f.get("kp"):
            continue
        if prev:
            for Li, Ri, is_leg in ((LEGS_L, LEGS_R, True), (ARMS_L, ARMS_R, False)):
                d = lambda a, b: math.hypot(f["kp"][a][0] - prev["kp"][b][0], f["kp"][a][1] - prev["kp"][b][1])
                normal = sum(d(a, a) + d(b, b) for a, b in zip(Li, Ri)); swapped = sum(d(a, b) + d(b, a) for a, b in zip(Li, Ri))
                if swapped < normal * 0.6 and normal > _bbox_h(f["kp"]) * 0.15:
                    for a, b in zip(Li, Ri):
                        f["kp"][a], f["kp"][b] = f["kp"][b], f["kp"][a]
                        if f.get("world"):
                            f["world"][a], f["world"][b] = f["world"][b], f["world"][a]
                    if is_leg and s.get("ski"):
                        s["ski"] = {"L": s["ski"]["R"], "R": s["ski"]["L"], "shared": s["ski"]["shared"]}
                    f.setdefault("flags", []).append("lr_swapped_" + ("legs" if is_leg else "arms"))
                    swaps += 1
        prev = f
    return swaps


def joint_quality(frames: list[dict[str, Any]]) -> int:
    """q[j] = 可視度。1 コマだけ飛んだ関節は前後の平均で置き換え q を 0.55 以下にする。"""
    spikes = 0
    for f in frames:
        f["q"] = [min(1.0, max(0.0, p[2])) for p in f["kp"]] if f.get("kp") else None
    for i in range(1, len(frames) - 1):
        a, f, b = frames[i - 1], frames[i], frames[i + 1]
        if not (a.get("kp") and f.get("kp") and b.get("kp")):
            continue
        bh = _bbox_h(f["kp"])
        for j in range(len(f["kp"])):
            dp = math.hypot(f["kp"][j][0] - a["kp"][j][0], f["kp"][j][1] - a["kp"][j][1])
            dn = math.hypot(f["kp"][j][0] - b["kp"][j][0], f["kp"][j][1] - b["kp"][j][1])
            ds = math.hypot(b["kp"][j][0] - a["kp"][j][0], b["kp"][j][1] - a["kp"][j][1])
            if dp > 0.2 * bh and dn > 0.2 * bh and ds < 0.5 * min(dp, dn):
                f["kp"][j] = [(a["kp"][j][0] + b["kp"][j][0]) / 2, (a["kp"][j][1] + b["kp"][j][1]) / 2, f["kp"][j][2]]
                if f.get("world") and a.get("world") and b.get("world"):
                    f["world"][j] = [(a["world"][j][k] + b["world"][j][k]) / 2 for k in range(3)]
                f["q"][j] = min(f["q"][j], 0.55); spikes += 1
                f.setdefault("flags", []).append(f"spike_j{j}")
    return spikes


def fill_gaps(frames: list[dict[str, Any]], max_gap: int) -> int:
    filled = 0; i = 0; n = len(frames)
    while i < n:
        if frames[i].get("src") != "det":
            i += 1; continue
        j = i + 1
        while j < n and frames[j].get("src") != "det":
            j += 1
        if j < n and 1 < j - i <= max_gap + 1:
            A, B = frames[i], frames[j]
            for k in range(i + 1, j):
                u = (k - i) / (j - i)
                frames[k]["kp"] = [[p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u, min(p[2], q[2])] for p, q in zip(A["kp"], B["kp"])]
                frames[k]["world"] = [[p[m] + (q[m] - p[m]) * u for m in range(3)] for p, q in zip(A["world"], B["world"])] if A.get("world") and B.get("world") else None
                frames[k]["src"] = "interp"
                frames[k]["q"] = [min(a, b) * 0.7 for a, b in zip(A["q"], B["q"])]
                filled += 1
        i = j
    return filled


def one_euro_series(vals: list[float | None], dt: float, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> list[float | None]:
    def alpha(c):
        tau = 1 / (2 * math.pi * c); return 1 / (1 + tau / dt)

    def run(arr):
        out = [None] * len(arr); xp = None; dxp = 0.0
        for i, x in enumerate(arr):
            if x is None:
                xp = None; dxp = 0.0; continue
            if xp is None:
                out[i] = x; xp = x; continue
            ad = alpha(d_cutoff); dx = ad * (x - xp) / dt + (1 - ad) * dxp
            a = alpha(min_cutoff + beta * abs(dx))
            xf = a * x + (1 - a) * xp; out[i] = xf; xp = xf; dxp = dx
        return out

    f = run(vals); b = run(vals[::-1])[::-1]
    return [None if v is None else (f[i] + b[i]) / 2 for i, v in enumerate(vals)]


def smooth_all(frames: list[dict[str, Any]], dt: float, aspect: float) -> None:
    """kp → kpS、world → worldS を作る（元は残す）。"""
    n = len(frames)
    for f in frames:
        f["kpS"] = [p[:] for p in f["kp"]] if f.get("kp") else None
        f["worldS"] = [p[:] for p in f["world"]] if f.get("world") else None
    if not n:
        return
    nk = max((len(f["kp"]) for f in frames if f.get("kp")), default=0)
    for j in range(nk):
        for key, dims, minc, beta in (("kpS", (0, 1), 1.2, 2.0), ("worldS", (0, 1, 2), 1.2, 1.0)):
            for d in dims:
                sc = aspect if (key == "kpS" and d == 0) else 1.0
                series = [f[key][j][d] * sc if f.get(key) and len(f[key]) > j else None for f in frames]
                sm = one_euro_series(series, dt, minc, beta)
                for i, f in enumerate(frames):
                    if f.get(key) and len(f[key]) > j and sm[i] is not None:
                        f[key][j][d] = sm[i] / sc


class TemporalStage:
    name = "temporal"

    def run(self, ctx, data):
        pf = data["perframe"]
        frames = [dict(f) for f in pf["frames"]]
        for f in frames:
            if f.get("kp"):
                f["kp"] = [p[:] for p in f["kp"]]
            if f.get("world"):
                f["world"] = [p[:] for p in f["world"]]
        skis = [dict(s) for s in pf["ski"]]
        fps = ctx.scratch["sample_fps"]; dt = 1 / fps
        swaps = fix_left_right(frames, skis)
        spikes = joint_quality(frames)
        filled = fill_gaps(frames, max(2, round(fps * 0.4)))
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        smooth_all(frames, dt, vw / vh if vh else 1.0)
        for f, s in zip(frames, skis):
            f["ski"] = s.get("ski") if f.get("src") == "det" else None
        ctx.scratch["frames"] = frames
        return {"frames": frames, "summary": {"lr_swaps": swaps, "spikes": spikes, "interpolated": filled,
                                              "detected": sum(1 for f in frames if f.get("src") == "det"), "missing": sum(1 for f in frames if not f.get("src"))}}
