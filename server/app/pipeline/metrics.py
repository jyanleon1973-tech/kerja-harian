"""指標の計算。各指標に値・分類（obs=画像から直接観測 / est=推定 / na=測定不可）・信頼度（依存関節の確からしさの最小）を付ける。
2D 画像座標（撮影方向ごと）を一次情報とし、3D（BlazePose world）は est に限定する。cm 断定はしない（身長比 % と角度）。"""
from __future__ import annotations

import math
from typing import Any

# de Leva (1996) 成人男性。(質量比, 近位点群, 遠位点群, 近位からの重心位置比)
SEG_MASS = [
    (0.0694, (7, 8), (7, 8), 0.5), (0.4346, (11, 12), (23, 24), 0.45),
    (0.0271, (11,), (13,), 0.577), (0.0271, (12,), (14,), 0.577), (0.0162, (13,), (15,), 0.457), (0.0162, (14,), (16,), 0.457),
    (0.0061, (15,), (19,), 0.79), (0.0061, (16,), (20,), 0.79), (0.1416, (23,), (25,), 0.41), (0.1416, (24,), (26,), 0.41),
    (0.0433, (25,), (27,), 0.44), (0.0433, (26,), (28,), 0.44), (0.0137, (29,), (31,), 0.44), (0.0137, (30,), (32,), 0.44),
]
QMIN = 0.4
SKI_MIN = 0.55


def cog2d(kp, vw, vh):
    x = y = m = 0.0
    for mass, a, b, f in SEG_MASS:
        ax = sum(kp[i][0] for i in a) / len(a) * vw; ay = sum(kp[i][1] for i in a) / len(a) * vh
        bx = sum(kp[i][0] for i in b) / len(b) * vw; by = sum(kp[i][1] for i in b) / len(b) * vh
        x += mass * (ax + (bx - ax) * f); y += mass * (ay + (by - ay) * f); m += mass
    return x / m, y / m


def _deg(r): return r * 180 / math.pi


def compute_metrics(f: dict[str, Any], view: str, turn: int | None, vw: int, vh: int, roll_deg: float = 0.0) -> dict[str, Any] | None:
    kp = f.get("kpS"); q = f.get("q"); w = f.get("worldS")
    if not kp or not q:
        return None
    cx, cy = vw / 2, vh / 2; cr, sr = math.cos(-math.radians(roll_deg)), math.sin(-math.radians(roll_deg))
    P = []
    for p in kp:
        x, y = p[0] * vw - cx, p[1] * vh - cy
        P.append((x * cr - y * sr + cx, x * sr + y * cr + cy))
    m2 = lambda ids: (sum(P[i][0] for i in ids) / len(ids), sum(P[i][1] for i in ids) / len(ids))
    sh, hip, ank, ear, feet = m2((11, 12)), m2((23, 24)), m2((27, 28)), m2((7, 8)), m2((27, 28, 29, 30, 31, 32))
    dist = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])
    leg = (dist(P[23], P[25]) + dist(P[25], P[27]) + dist(P[24], P[26]) + dist(P[26], P[28])) / 2
    BH = max(1.0, leg + dist(hip, sh) + dist(sh, ear) * 1.3)
    cog = cog2d(kp, vw, vh)
    qmin = lambda ids: min(q[i] for i in ids)
    right_sign = -1 if view == "front" else 1
    facing = (1 if P[0][0] > hip[0] else -1) if q[0] > 0.5 else (1 if (P[31][0] + P[32][0]) > (P[29][0] + P[30][0]) else -1)
    in_sign = turn or 0
    frontal = view in ("front", "back")
    M: dict[str, dict[str, Any]] = {}

    def put(key, v, cls, conf=1.0):
        ok = v is not None and isinstance(v, (int, float)) and math.isfinite(v)
        rec = {"v": float(v) if ok else None, "cls": cls, "conf": round(float(conf), 3)}
        if cls != "na" and conf < QMIN:
            rec["v"] = None; rec["low"] = True
        M[key] = rec

    na = lambda key: put(key, None, "na", 1.0)
    ang2 = lambda A, B, C: _deg(math.acos(max(-1, min(1, ((P[A][0] - P[B][0]) * (P[C][0] - P[B][0]) + (P[A][1] - P[B][1]) * (P[C][1] - P[B][1])) / ((dist(P[A], P[B]) * dist(P[C], P[B])) or 1)))))
    def line_tilt(L, R):
        a, b = P[L], P[R]; re, le = (a, b) if a[0] > b[0] else (b, a)
        return _deg(math.atan2(re[1] - le[1], abs(re[0] - le[0]) or 1e-6)) * right_sign
    vert = lambda frm, to: _deg(math.atan2(to[0] - frm[0], frm[1] - to[1]))
    # 3D（推定用）
    P3 = None
    if w:
        P3 = [(p[0], -p[1], -p[2]) for p in w]
    def ang3(A, B, C):
        u = [P3[A][k] - P3[B][k] for k in range(3)]; v = [P3[C][k] - P3[B][k] for k in range(3)]
        nu = math.sqrt(sum(x * x for x in u)) or 1; nv = math.sqrt(sum(x * x for x in v)) or 1
        return _deg(math.acos(max(-1, min(1, sum(a * b for a, b in zip(u, v)) / (nu * nv)))))
    fwd3 = None
    if P3:
        rx, rz = P3[24][0] - P3[23][0], P3[24][2] - P3[23][2]; fx, fz = -rz, rx  # 前 = 上×右（y 上向き）→ 符号確認: up(0,1,0)×right(rx,0,rz) = (rz, 0, -rx)
        fx, fz = rz, -rx
        n = math.hypot(fx, fz); fwd3 = (fx / n, fz / n) if n > 1e-6 else None
    def in_plane3(vec, axis):
        return _deg(math.atan2(vec[0] * axis[0] + vec[2] * axis[1], vec[1]))

    # ===== 上半身 =====
    if frontal or view == "oblique":
        c = "est" if view == "oblique" else "obs"
        put("shoulderTilt", line_tilt(11, 12), c, qmin((11, 12)))
        put("pelvisTilt", line_tilt(23, 24), c, qmin((23, 24)))
        put("shoulderPelvisDiff", (M["shoulderTilt"]["v"] - M["pelvisTilt"]["v"]) if M["shoulderTilt"]["v"] is not None and M["pelvisTilt"]["v"] is not None else None, c, qmin((11, 12, 23, 24)))
        put("trunkLat", vert(hip, sh) * right_sign, c, qmin((11, 12, 23, 24)))
        put("lean", vert(feet, cog) * right_sign, "est", qmin((23, 24, 27, 28)) * (0.8 if view == "oblique" else 1))
        put("angulation", (M["lean"]["v"] - M["trunkLat"]["v"]) * (in_sign or 1) if M["lean"]["v"] is not None and M["trunkLat"]["v"] is not None else None, "est", min(M["lean"]["conf"], M["trunkLat"]["conf"]) * (1 if in_sign else 0.6))
    else:
        for k in ("shoulderTilt", "pelvisTilt", "shoulderPelvisDiff", "trunkLat", "lean", "angulation"): na(k)
    if view == "side":
        put("trunkFwd", vert(hip, sh) * facing, "obs", qmin((11, 12, 23, 24)))
    elif view == "oblique" and P3 and fwd3:
        tv = [(P3[11][k] + P3[12][k]) / 2 - (P3[23][k] + P3[24][k]) / 2 for k in range(3)]
        put("trunkFwd", in_plane3(tv, fwd3), "est", qmin((11, 12, 23, 24)) * 0.8)
    else:
        na("trunkFwd")
    if P3:
        yaw = lambda vx, vz: math.atan2(vx, -vz)
        tw = _deg(yaw(P3[12][0] - P3[11][0], P3[12][2] - P3[11][2]) - yaw(P3[24][0] - P3[23][0], P3[24][2] - P3[23][2]))
        tw = ((tw + 540) % 360) - 180
        put("torsoTwist", tw, "est", qmin((11, 12, 23, 24)) * 0.8)
        put("counter", -tw * in_sign if in_sign else None, "est", M["torsoTwist"]["conf"] * (1 if in_sign else 0))
    else:
        na("torsoTwist"); na("counter")
    # ===== 下半身 =====
    if view == "side":
        put("kneeL", 180 - ang2(23, 25, 27), "obs", qmin((23, 25, 27))); put("kneeR", 180 - ang2(24, 26, 28), "obs", qmin((24, 26, 28)))
        put("hipL", 180 - ang2(11, 23, 25), "obs", qmin((11, 23, 25))); put("hipR", 180 - ang2(12, 24, 26), "obs", qmin((12, 24, 26)))
        put("shinL", vert(P[27], P[25]) * facing, "obs", qmin((25, 27))); put("shinR", vert(P[28], P[26]) * facing, "obs", qmin((26, 28)))
        put("kneeOverAnkleL", (P[25][0] - P[27][0]) * facing / BH * 100, "obs", qmin((25, 27))); put("kneeOverAnkleR", (P[26][0] - P[28][0]) * facing / BH * 100, "obs", qmin((26, 28)))
        put("foreAft", (P[27][0] - P[28][0]) * facing / BH * 100, "obs", qmin((27, 28)))
        na("stance"); na("kneeInL"); na("kneeInR")
    else:
        if P3 and fwd3:
            k = 0.8
            put("kneeL", 180 - ang3(23, 25, 27), "est", qmin((23, 25, 27)) * k); put("kneeR", 180 - ang3(24, 26, 28), "est", qmin((24, 26, 28)) * k)
            put("hipL", 180 - ang3(11, 23, 25), "est", qmin((11, 23, 25)) * k); put("hipR", 180 - ang3(12, 24, 26), "est", qmin((12, 24, 26)) * k)
            sl = [P3[25][i] - P3[27][i] for i in range(3)]; sr_ = [P3[26][i] - P3[28][i] for i in range(3)]
            put("shinL", in_plane3(sl, fwd3), "est", qmin((25, 27)) * k); put("shinR", in_plane3(sr_, fwd3), "est", qmin((26, 28)) * k)
            put("kneeOverAnkleL", (sl[0] * fwd3[0] + sl[2] * fwd3[1]) / 1.7 * 100, "est", qmin((25, 27)) * k); put("kneeOverAnkleR", (sr_[0] * fwd3[0] + sr_[2] * fwd3[1]) / 1.7 * 100, "est", qmin((26, 28)) * k)
            fa = [P3[27][i] - P3[28][i] for i in range(3)]
            put("foreAft", (fa[0] * fwd3[0] + fa[2] * fwd3[1]) / 1.7 * 100, "est", qmin((27, 28)) * k)
        else:
            for k in ("kneeL", "kneeR", "hipL", "hipR", "shinL", "shinR", "kneeOverAnkleL", "kneeOverAnkleR", "foreAft"): na(k)
        if frontal or view == "oblique":
            c = "est" if view == "oblique" else "obs"
            put("stance", abs(P[27][0] - P[28][0]) / BH * 100, c, qmin((27, 28)))
            put("kneeInL", (P[25][0] - P[27][0]) * right_sign / BH * 100, c, qmin((25, 27))); put("kneeInR", (P[26][0] - P[28][0]) * right_sign / BH * 100, c, qmin((26, 28)))
        else:
            na("stance"); na("kneeInL"); na("kneeInR")
    put("kneeAsym", (M["kneeL"]["v"] - M["kneeR"]["v"]) if M["kneeL"]["v"] is not None and M["kneeR"]["v"] is not None else None, M["kneeL"]["cls"], min(M["kneeL"]["conf"], M["kneeR"]["conf"]))
    put("hipHeight", (ank[1] - hip[1]) / leg * 100 if leg > 1 else None, "est" if view == "oblique" else "obs", qmin((23, 24, 27, 28)))
    # ===== 重心（推定） =====
    if view == "side":
        put("cogFwd", (cog[0] - ank[0]) * facing / BH * 100, "est", qmin((23, 24, 27, 28, 11, 12))); na("cogLat")
    elif frontal or view == "oblique":
        na("cogFwd"); put("cogLat", (cog[0] - feet[0]) * right_sign / BH * 100, "est", qmin((23, 24, 27, 28, 11, 12)) * (0.7 if view == "oblique" else 1))
    else:
        na("cogFwd"); na("cogLat")
    put("cogIn", M["cogLat"]["v"] * in_sign if in_sign and M["cogLat"]["v"] is not None else None, M["cogLat"]["cls"], M["cogLat"]["conf"] * (1 if in_sign else 0))
    # ===== 板（映像から検出できたもののみ） =====
    sk = f.get("ski") or {}
    skL = sk.get("L") if sk.get("L") and sk["L"]["conf"] >= SKI_MIN else None
    skR = sk.get("R") if sk.get("R") and sk["R"]["conf"] >= SKI_MIN and not sk.get("shared") else None
    ski_ang = lambda s: ((-_deg(s["ang"]) + 90) % 180 + 180) % 180 - 90
    if skL: put("skiAngL", ski_ang(skL), "obs", skL["conf"])
    else: na("skiAngL")
    if skR: put("skiAngR", ski_ang(skR), "obs", skR["conf"])
    else: na("skiAngR")
    if skL and skR and (frontal or view == "oblique"):
        def up_ang(s):
            vx, vy = math.cos(s["ang"]), math.sin(s["ang"])
            if vy > 0: vx, vy = -vx, -vy
            return math.atan2(-vy, vx)
        put("skiOpen", _deg(up_ang(skR) - up_ang(skL)) * right_sign, "est" if view == "oblique" else "obs", min(skL["conf"], skR["conf"]))
        put("cogSkiLat", (cog[0] - (skL["fx"] + skR["fx"]) / 2) * right_sign / BH * 100, "est", min(skL["conf"], skR["conf"]) * qmin((23, 24, 11, 12)))
    else:
        na("skiOpen"); na("cogSkiLat")
    return {"M": M, "cog2": [round(cog[0], 1), round(cog[1], 1)], "feet2": [round(feet[0], 1), round(feet[1], 1)], "BH": round(BH, 1), "facing": facing, "right_sign": right_sign}


class MetricsStage:
    name = "metrics"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]; view = ctx.scratch["view"]; turn = ctx.scratch["turn"]
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        roll = float(ctx.params.get("roll_deg", 0) or 0)
        out = [compute_metrics(f, view, turn[i], vw, vh, roll) for i, f in enumerate(frames)]
        ctx.scratch["metrics"] = out
        keys = sorted({k for m in out if m for k in m["M"]})
        avail = {k: sum(1 for m in out if m and m["M"][k]["v"] is not None) for k in keys}
        return {"metrics": out, "summary": {"frames_with_metrics": sum(1 for m in out if m), "available_counts": avail}}
