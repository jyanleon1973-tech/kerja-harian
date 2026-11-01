"""ターン判定。単一コマの姿勢ではなく複数の時系列手掛かりを合成する。
手掛かり: (1) 3D 推定の骨盤向きの回転速度、(2) カメラ動作を差し引いた選手軌跡の進行方向の変化、
(3) 正面・背面での足元→重心の横方向の傾き、(4) 板の画像上の向きの変化。
手掛かりが弱い・矛盾するときは 0（直進/切り替え）、手掛かりが無いときは None（不明）。"""
from __future__ import annotations

import math
from typing import Any

from .metrics import SEG_MASS, cog2d


def _yaw_rate_3d(frames, dt, k):
    fw = []
    for f in frames:
        w = f.get("worldS")
        if not w:
            fw.append(None); continue
        rx, rz = w[24][0] - w[23][0], w[24][2] - w[23][2]           # 左腰→右腰（x 右, z 奥行き）
        fx, fz = -rz, rx                                              # 前 = 上 × 右（y 下向き系なので符号に注意）
        tx = (w[31][0] - w[29][0]) + (w[32][0] - w[30][0]); tz = (w[31][2] - w[29][2]) + (w[32][2] - w[30][2])
        n = math.hypot(fx, fz)
        if n < 1e-6:
            fw.append(None); continue
        fx, fz = fx / n, fz / n
        if math.hypot(tx, tz) > 1e-3 and (fx * tx + fz * tz) / math.hypot(tx, tz) < -0.5:
            fx, fz = -fx, -fz
        fw.append((fx, fz))
    prev = None
    for i, v in enumerate(fw):
        if v is None:
            continue
        if prev and (v[0] * prev[0] + v[1] * prev[1]) < 0:
            fw[i] = (-v[0], -v[1])
        prev = fw[i]
    rate = []
    for i in range(len(fw)):
        a = fw[max(0, i - k)]; b = fw[min(len(fw) - 1, i + k)]
        if not a or not b or not fw[i]:
            rate.append(None); continue
        cross = a[0] * b[1] - a[1] * b[0]     # 上から見た回転（符号は座標系依存。下で向きを統一）
        rate.append(math.degrees(math.asin(max(-1, min(1, cross)))) / (2 * k * dt))
    return rate


def _heading_rate(traj, dt, k, vw):
    """画像上の軌跡（カメラ補正済み）の進行方向変化（deg/s）。移動が小さいときは None。"""
    out = []
    n = len(traj)
    for i in range(n):
        a = traj[max(0, i - k)]; m = traj[i]; b = traj[min(n - 1, i + k)]
        if not a or not m or not b:
            out.append(None); continue
        v1 = (m["x"] - a["x"], m["y"] - a["y"]); v2 = (b["x"] - m["x"], b["y"] - m["y"])
        if math.hypot(*v1) < vw * 0.01 or math.hypot(*v2) < vw * 0.01:
            out.append(None); continue
        ang = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]))
        out.append(ang / (k * dt))
    return out


def _lean_sign(frames, view, vw, vh):
    out = []
    for f in frames:
        kp = f.get("kpS")
        if not kp or view not in ("front", "back"):
            out.append(None); continue
        c = cog2d(kp, vw, vh)
        fx = sum(kp[j][0] for j in (27, 28, 29, 30, 31, 32)) / 6 * vw
        d = (c[0] - fx) / max(1.0, (max(p[1] for p in kp) - min(p[1] for p in kp)) * vh)
        out.append(d * (1 if view == "back" else -1))   # 選手の右へ傾くと正
    return out


def _median_filter(arr, w):
    out = list(arr)
    for i in range(len(arr)):
        win = [arr[j] for j in range(max(0, i - w), min(len(arr), i + w + 1)) if arr[j] is not None]
        out[i] = sorted(win)[len(win) // 2] if win else None
    return out


class TurnStage:
    name = "turns"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]; traj = ctx.scratch["traj"]; view = ctx.scratch["view"]
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        fps = ctx.scratch["sample_fps"]; dt = 1 / fps; k = max(1, round(0.35 / dt))
        yaw = _yaw_rate_3d(frames, dt, k)
        head = _heading_rate(traj, dt, k, vw)
        lean = _lean_sign(frames, view, vw, vh)
        lean = _median_filter(lean, k)
        n = len(frames)
        votes, turn = [], []
        for i in range(n):
            cues = {}
            if yaw[i] is not None:
                cues["pelvis_yaw"] = -1 if yaw[i] > 12 else (1 if yaw[i] < -12 else 0)
            if head[i] is not None and view != "side":
                # 画像座標（y 下向き）で時計回りが正 → 背面では右ターン、正面では左ターン
                s = 1 if head[i] > 25 else (-1 if head[i] < -25 else 0)
                cues["trajectory"] = s if view == "back" else (-s if view == "front" else 0)
            if lean[i] is not None:
                cues["lean"] = 1 if lean[i] > 0.03 else (-1 if lean[i] < -0.03 else 0)
            votes.append(cues)
            if not cues:
                turn.append(None); continue
            vals = [v for v in cues.values()]
            s = sum(vals)
            nonzero = [v for v in vals if v]
            if nonzero and len(set(nonzero)) > 1:      # 手掛かりが矛盾
                turn.append(0)
            elif abs(s) >= max(1, math.ceil(len(vals) / 2)):
                turn.append(1 if s > 0 else -1)
            else:
                turn.append(0)
        # ちらつき除去（0.3 秒未満の区間は前の状態に吸収）
        min_len = max(2, round(0.3 / dt))
        for _ in range(2):
            i = 0
            while i < n:
                j = i
                while j < n and turn[j] == turn[i]:
                    j += 1
                if j - i < min_len and i > 0:
                    for q in range(i, j):
                        turn[q] = turn[i - 1]
                i = j
        segments, phase = [], [None] * n
        i = 0
        while i < n:
            j = i
            while j < n and turn[j] == turn[i]:
                j += 1
            if turn[i] not in (0, None):
                segments.append({"dir": turn[i], "start": i, "end": j - 1, "t0": frames[i]["t"], "t1": frames[j - 1]["t"]})
                for q in range(i, j):
                    phase[q] = min(2, int(3 * (q - i) / (j - i)))
            i = j
        # 切り替え点: 符号が変わる境界
        switches = [{"i": segments[s + 1]["start"], "t": frames[segments[s + 1]["start"]]["t"]} for s in range(len(segments) - 1) if segments[s]["dir"] != segments[s + 1]["dir"]]
        ctx.scratch["turn"] = turn; ctx.scratch["phase"] = phase; ctx.scratch["segments"] = segments
        return {"turn": turn, "phase": phase, "segments": segments, "switches": switches,
                "cues": {"pelvis_yaw_rate": yaw, "heading_rate": head, "lean": lean, "votes": votes},
                "summary": {"turns": len(segments), "left": sum(1 for s in segments if s["dir"] < 0), "right": sum(1 for s in segments if s["dir"] > 0),
                            "unknown_frames": sum(1 for t in turn if t is None)}}
