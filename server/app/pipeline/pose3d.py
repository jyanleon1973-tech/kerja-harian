"""3D 姿勢の拘束付き補正と、3D スキー板の復元。
入力の 3D は差し替え可能な「3D 源」（既定: BlazePose world。将来: MotionBERT / RTMW3D）。2D を単純に 3D へ変換することはしない。
処理: 骨長の正規化 → 関節可動域の拘束（膝の蝶番・過伸展禁止、股関節の範囲）→ 接地（雪面）→ 向きと移動 → 板・ブーツの接続 → 信頼度。
座標系: Y 上、X = 画像の右、Z = カメラ側（撮影方向から見た向き）。単位は体型正規化の m（実寸ではない）。"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .temporal import one_euro_series

# 親 → 子 の骨（BlazePose 33 点）。腰中点を根にする
BONES = [(23, 25), (25, 27), (27, 29), (27, 31), (24, 26), (26, 28), (28, 30), (28, 32),
         (11, 13), (13, 15), (15, 19), (12, 14), (14, 16), (16, 20)]
L_IDX = {23, 25, 27, 29, 31, 11, 13, 15, 17, 19, 21}


class Pose3DSource:
    """3D 源の共通形式: frames[i]["worldS"]（33×3、腰原点、y 下向き）を返す。"""
    name = "blazepose_world"
    version = "mediapipe world landmarks"

    def joints(self, frames) -> list[np.ndarray | None]:
        out = []
        for f in frames:
            w = f.get("worldS")
            out.append(np.array([[p[0], -p[1], -p[2]] for p in w], dtype=float) if w else None)  # Y 上・Z カメラ側へ
        return out


class LiftingSourceStub(Pose3DSource):
    """2D 系列 → 3D 系列（MotionBERT 等）の差し替え口。重みが無いため未実装。"""
    name = "lifting_stub"
    version = "not available"

    def joints(self, frames):
        raise NotImplementedError("3D リフティングモデルは未導入（GPU 承認後に組み込む）")


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def normalize_bone_lengths(J: np.ndarray, med: dict[tuple[int, int], float]) -> np.ndarray:
    """骨長を動画全体の中央値に揃える（根から順に子を置き直す）。"""
    out = J.copy()
    pel = (J[23] + J[24]) / 2
    hipw = med.get((23, 24), np.linalg.norm(J[24] - J[23]))
    d = _unit(J[24] - J[23]); out[23] = pel - d * hipw / 2; out[24] = pel + d * hipw / 2
    shc = (J[11] + J[12]) / 2
    tlen = med.get(("torso",), np.linalg.norm(shc - pel))
    shc2 = pel + _unit(shc - pel) * tlen
    shw = med.get((11, 12), np.linalg.norm(J[12] - J[11]))
    ds = _unit(J[12] - J[11]); out[11] = shc2 - ds * shw / 2; out[12] = shc2 + ds * shw / 2
    for a, b in BONES:
        out[b] = out[a] + _unit(J[b] - J[a]) * med.get((a, b), np.linalg.norm(J[b] - J[a]))
    # 頭部: 肩中心からの相対位置をそのまま平行移動
    shift = shc2 - shc
    for j in range(0, 11):
        out[j] = J[j] + shift
    return out


def pelvis_frame(J: np.ndarray):
    right = J[24] - J[23]; right[1] = 0; right = _unit(right)
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.cross(up, right)
    return fwd, right, up


def clamp_knee(J: np.ndarray, hip: int, knee: int, ankle: int, fwd: np.ndarray, lo_deg=15.0, hi_deg=177.0) -> float:
    """膝の内角を [lo, hi] に射影。過伸展は前方へ曲げる。戻り値: 修正量（度）。"""
    fixed = 0.0
    # 過伸展（膝が股関節-足首の線より後ろ）: 膝をその線に対して前へ鏡映する（骨長は保たれる）
    ha = J[ankle] - J[hip]; lha = np.linalg.norm(ha)
    if lha > 1e-6:
        tpar = float(np.dot(J[knee] - J[hip], ha)) / (lha * lha)
        foot = J[hip] + ha * tpar
        d = J[knee] - foot
        if np.dot(d, fwd) < -1e-3:
            J[knee] = foot - d
            fixed += math.degrees(2 * math.atan2(np.linalg.norm(d), max(1e-6, lha / 2)))
    u = J[hip] - J[knee]; v = J[ankle] - J[knee]
    lu, lv = np.linalg.norm(u), np.linalg.norm(v)
    if lu < 1e-6 or lv < 1e-6:
        return fixed
    ang = math.degrees(math.acos(max(-1, min(1, float(np.dot(u, v)) / (lu * lv)))))
    target = min(hi_deg, max(lo_deg, ang))
    if abs(target - ang) < 1e-6:
        return fixed
    # 回転軸: 大腿と下腿の面の法線。伸びきりに近い場合は前後方向を使う（膝は前に曲がる）
    axis = np.cross(u, v)
    if np.linalg.norm(axis) < 1e-6 * lu * lv or ang > 170:
        axis = np.cross(u, fwd)
    axis = _unit(axis)
    rot = math.radians(target - ang)
    # v を axis まわりに回転（ロドリゲス）
    vr = v * math.cos(rot) + np.cross(axis, v) * math.sin(rot) + axis * np.dot(axis, v) * (1 - math.cos(rot))
    # 足首が膝より前に来る向き（前方）を選ぶ: 2 方向のうち前方成分が大きい方
    vr2 = v * math.cos(-rot) + np.cross(axis, v) * math.sin(-rot) + axis * np.dot(axis, v) * (1 - math.cos(-rot))
    cand = vr if np.dot(vr - v, fwd) >= np.dot(vr2 - v, fwd) else vr2
    delta = cand - v
    for j in (ankle, ankle + 2, ankle + 4):   # 足首・かかと・つま先を一緒に動かす
        J[j] = J[j] + delta
    return fixed + abs(target - ang)


def clamp_hip(J: np.ndarray, hip: int, knee: int, side_sign: float, fwd, right, up, flex=(-30, 130), abd=(-40, 60)) -> float:
    """股関節: 屈曲 [-30°, 130°]、外転 [-40°, 60°] に射影。戻り値: 修正量（度）。"""
    t = J[knee] - J[hip]; L = np.linalg.norm(t)
    if L < 1e-6:
        return 0.0
    tf, tu, tr = float(np.dot(t, fwd)), float(np.dot(t, up)), float(np.dot(t, right)) * side_sign
    fl = math.degrees(math.atan2(tf, -tu)); ab = math.degrees(math.asin(max(-1, min(1, tr / L))))
    fl2 = min(flex[1], max(flex[0], fl)); ab2 = min(abd[1], max(abd[0], ab))
    if abs(fl2 - fl) < 1e-6 and abs(ab2 - ab) < 1e-6:
        return 0.0
    ca = math.cos(math.radians(ab2))
    new = (fwd * math.sin(math.radians(fl2)) * ca - up * math.cos(math.radians(fl2)) * ca + right * side_sign * math.sin(math.radians(ab2))) * L
    delta = new - t
    for j in (knee, knee + 2, knee + 4, knee + 6):   # 膝・足首・かかと・つま先
        J[j] = J[j] + delta
    return max(abs(fl2 - fl), abs(ab2 - ab))


def fit_weak_perspective(J: np.ndarray, kp: list, q: list, vw: int, vh: int):
    """3D → 2D の弱透視当てはめ。戻り値: (A 2x3, b 2, RMS 残差 px)。"""
    ids = [i for i in range(11, 29) if q[i] > 0.5]
    if len(ids) < 6:
        return None
    X = np.array([J[i] for i in ids]); U = np.array([[kp[i][0] * vw, kp[i][1] * vh] for i in ids])
    Xh = np.hstack([X, np.ones((len(ids), 1))])
    sol, *_ = np.linalg.lstsq(Xh, U, rcond=None)
    pred = Xh @ sol
    rms = float(np.sqrt(((pred - U) ** 2).sum(axis=1).mean()))
    return sol[:3].T, sol[3], rms


class Pose3DStage:
    name = "pose3d"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]; metrics = ctx.scratch["metrics"]; view = ctx.scratch["view"]
        vw, vh = data["decode"]["video"]["width"], data["decode"]["video"]["height"]
        fps = ctx.scratch["sample_fps"]; dt = 1 / fps; n = len(frames)
        cam = data["perframe"]["camera"]; traj = ctx.scratch["traj"]
        src = Pose3DSource()
        ctx.model_versions["pose3d_source"] = f"{src.name}: {src.version}"
        ctx.model_versions["pose3d_refine"] = "constraints_v1(bone-length,knee-hinge,hip-range,ground,ski-attach)"
        raw = src.joints(frames)
        # 骨長の中央値
        lens: dict = {}
        for J in raw:
            if J is None:
                continue
            for a, b in BONES + [(23, 24), (11, 12)]:
                lens.setdefault((a, b), []).append(float(np.linalg.norm(J[b] - J[a])))
            lens.setdefault(("torso",), []).append(float(np.linalg.norm((J[11] + J[12]) / 2 - (J[23] + J[24]) / 2)))
        med = {k: float(np.median(v)) for k, v in lens.items()}
        ski_len = float(ctx.params.get("ski_length_m") or 1.65)
        out = []
        fixes_total = 0
        for i in range(n):
            J0 = raw[i]; f = frames[i]
            if J0 is None or not f.get("q"):
                out.append(None); continue
            J = normalize_bone_lengths(J0, med)
            fwd, right, up = pelvis_frame(J)
            fix = clamp_hip(J, 23, 25, -1.0, fwd, right, up) + clamp_hip(J, 24, 26, 1.0, fwd, right, up)
            fix += clamp_knee(J, 23, 25, 27, fwd) + clamp_knee(J, 24, 26, 28, fwd)
            fixes_total += 1 if fix > 1 else 0
            # 接地: 足部の最下点を地面へ（時間方向の中央値は後で）
            floor = float(min(J[k][1] for k in (27, 28, 29, 30, 31, 32)))
            # 再投影の整合
            fit = fit_weak_perspective(J, f["kpS"], f["q"], vw, vh)
            BH = metrics[i]["BH"] if metrics[i] else max(1.0, vh * 0.5)
            reproj = fit[2] / BH if fit else None
            # 奥行き方向の割合（画面に直交する成分が多いほど不確か）
            depth_frac = float(np.mean([abs(J[b][2] - J[a][2]) / max(1e-6, np.linalg.norm(J[b] - J[a])) for a, b in BONES]))
            q = f["q"]; qcore = min(q[j] for j in (11, 12, 23, 24, 25, 26, 27, 28))
            conf = qcore * (0.7 if f.get("src") == "interp" else 1.0) * (1 - min(1.0, (reproj or 0) / 0.08) * 0.5) * (1 - 0.4 * depth_frac) * (0.85 if fix > 15 else 1.0)
            # ブーツと板
            skis = {}
            for key, ank, heel, toe, s2d in (("L", 27, 29, 31, "L"), ("R", 28, 30, 32, "R")):
                boot = (J[ank] + J[heel] + J[toe]) / 3
                fd = J[toe] - J[heel]; fd[1] = 0
                fd = _unit(fd) if np.linalg.norm(fd) > 1e-6 else fwd.copy()
                if np.dot(fd, fwd) < 0:
                    fd = -fd
                d = _unit(0.55 * fd + 0.45 * fwd)        # 足部の向きと骨盤の前方の合成（事前情報）
                ssrc = "foot+pelvis"; sconf = 0.45 * qcore
                line = (f.get("ski") or {}).get(s2d)
                # 2D の板の線と整合する向きを選ぶ（カメラに俯角があり、投影が向きを区別できる場合のみ）
                if line and line["conf"] >= 0.55 and fit:
                    A = fit[0]
                    def proj_ang(v3):
                        p = A @ np.array([v3[0], 0, v3[2]]); return math.atan2(p[1], p[0]), np.linalg.norm(p)
                    base = math.atan2(d[2], d[0])
                    best, best_cost = d, 1e9
                    for deg in range(-60, 61, 5):
                        th = base + math.radians(deg); c = np.array([math.cos(th), 0, math.sin(th)])
                        pa, plen = proj_ang(c)
                        dd = abs((pa - line["ang"]) % math.pi); dd = min(dd, math.pi - dd)
                        cost = dd + math.radians(abs(deg)) * 0.15
                        if cost < best_cost:
                            best, best_cost = c, cost
                    # 向きの識別力: 投影長が候補間で十分変わるか（側面・水平カメラでは区別できない）
                    lens_ = [proj_ang(np.array([math.cos(base + math.radians(g)), 0, math.sin(base + math.radians(g))]))[1] for g in (-45, 0, 45)]
                    discrim = (max(lens_) - min(lens_)) / max(1e-6, max(lens_))
                    if discrim > 0.15 and best_cost < math.radians(12):
                        d = _unit(np.array([best[0], 0, best[2]])); ssrc = "edge2d+foot"; sconf = min(1.0, line["conf"] * 0.8 + 0.2 * qcore)
                center = boot.copy(); center[1] = floor
                skis[key] = {"center": [round(float(x), 4) for x in center], "dir": [round(float(d[0]), 4), round(float(d[2]), 4)], "len": ski_len,
                             "boot": [round(float(x), 4) for x in boot], "conf": round(float(sconf), 3), "src": ssrc}
            # 左右の板の交差（上から見た線分の交差）
            cross = False
            if "L" in skis and "R" in skis:
                def seg(s):
                    c = np.array([s["center"][0], s["center"][2]]); dd = np.array(s["dir"]) * s["len"] / 2; return c - dd, c + dd
                p1, p2 = seg(skis["L"]); p3, p4 = seg(skis["R"])
                def ccw(a, b, c): return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
                cross = bool(ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4))
            flags = []
            if cross: flags.append("ski_cross")
            if reproj is not None and reproj > 0.08: flags.append("reproj_high")
            if fix > 15: flags.append("joint_limit_fixed")
            out.append({"joints": np.round(J, 4).tolist(), "floor": round(floor, 4), "fwd": [round(float(fwd[0]), 4), round(float(fwd[2]), 4)],
                        "conf": round(float(max(0.0, min(1.0, conf))), 3), "reproj_bh": round(reproj, 4) if reproj is not None else None,
                        "depth_frac": round(depth_frac, 3), "fix_deg": round(fix, 1), "ski": skis, "flags": flags})
        # 地面高の時間方向中央値、根の位置（カメラ補正済み画像軌跡 → 体格比 m。奥行きは未知なので 0、信頼度低）
        fl = [p["floor"] if p else None for p in out]
        for i, p in enumerate(out):
            if not p:
                continue
            win = [fl[k] for k in range(max(0, i - 5), min(n, i + 6)) if fl[k] is not None]
            p["floor"] = round(float(np.median(win)), 4)
        # 画像面の移動を体格比 m に変換（身長 1.75 m 相当として BH px を使う）
        rx = [t["x"] if t else None for t in traj]; ry = [t["y"] if t else None for t in traj]
        sx = one_euro_series(rx, dt, 1.5, 0.5); sy = one_euro_series(ry, dt, 1.5, 0.5)
        x0 = next((v for v in sx if v is not None), 0.0); y0 = next((v for v in sy if v is not None), 0.0)
        facing = metrics[0]["facing"] if metrics and metrics[0] else 1
        for i, p in enumerate(out):
            if not p or sx[i] is None:
                continue
            BH = metrics[i]["BH"] if metrics[i] else vh * 0.5
            m_per_px = 1.75 / BH
            dx = (sx[i] - x0) * m_per_px; dy = (sy[i] - y0) * m_per_px
            if view == "side":
                root = [0.0, 0.0, 0.0]; root_fwd = dx * facing            # 画像の横 = 進行方向
                p["root"] = [round(dx, 3), 0.0, 0.0]; p["root_note"] = "側面: 画像横方向の移動のみ（奥行き不明）"
            elif view in ("front", "back"):
                # 正面: 画像の下へ = カメラへ近づく（Z+）、背面: 画像の下へ = 遠ざかる（Z−）
                p["root"] = [round(dx, 3), 0.0, round(dy * (1 if view == "front" else -1) * 1.5, 3)]; p["root_note"] = "正面/背面: 奥行きは画像縦方向からの粗い推定"
            else:
                p["root"] = [round(dx, 3), 0.0, round(dy * 1.0, 3)]; p["root_note"] = "斜め: 画像面の移動（奥行き不明）"
            p["root_conf"] = round(0.5 * (0.6 if data["camera"]["camera_moving"] else 1.0), 2)
        ctx.scratch["pose3d"] = out
        valid = [p for p in out if p]
        return {"pose3d": out, "ski_length_m": ski_len, "axes": "Y up, X image-right, Z toward camera; units = body-normalized m",
                "summary": {"frames": len(valid), "mean_conf": round(float(np.mean([p["conf"] for p in valid])), 3) if valid else None,
                            "joint_limit_fixed": fixes_total, "ski_cross_frames": sum(1 for p in valid if "ski_cross" in p["flags"]),
                            "ski_dir_from_edge": sum(1 for p in valid for k in ("L", "R") if p["ski"].get(k, {}).get("src") == "edge2d+foot"),
                            "mean_reproj_bh": round(float(np.mean([p["reproj_bh"] for p in valid if p["reproj_bh"] is not None])), 4) if valid else None}}
