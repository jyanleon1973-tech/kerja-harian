"""3D 拘束付き補正のテスト（合成データ）。"""
import math

import numpy as np

from app.pipeline.pose3d import BONES, Pose3DStage, clamp_hip, clamp_knee, fit_weak_perspective, normalize_bone_lengths, pelvis_frame


def standing(knee_bend_deg=0.0, hyper=False):
    """Y 上、Z カメラ側。前方 = -Z（骨盤の前 = up × right、right = +X → fwd = (0,1,0)×(1,0,0) = (0,0,-1)）。"""
    J = np.zeros((33, 3))
    J[23] = [-0.1, 0.0, 0]; J[24] = [0.1, 0.0, 0]
    J[11] = [-0.18, 0.5, 0]; J[12] = [0.18, 0.5, 0]
    J[13] = [-0.25, 0.25, 0]; J[14] = [0.25, 0.25, 0]; J[15] = [-0.28, 0.0, 0]; J[16] = [0.28, 0.0, 0]; J[19] = [-0.3, -0.05, 0]; J[20] = [0.3, -0.05, 0]
    for hip, knee, ank, heel, toe, x in ((23, 25, 27, 29, 31, -0.1), (24, 26, 28, 30, 32, 0.1)):
        b = math.radians(knee_bend_deg)
        J[knee] = [x, -0.45, -0.45 * math.sin(b) * (-1 if hyper else 1)]
        J[ank] = [x, -0.9, 0.0]
        J[heel] = [x, -0.95, 0.05]; J[toe] = [x, -0.95, -0.15]
    J[0] = [0, 0.7, -0.05]; J[7] = [-0.07, 0.65, 0]; J[8] = [0.07, 0.65, 0]
    return J


def test_pelvis_frame_forward_is_minus_z():
    fwd, right, up = pelvis_frame(standing())
    assert np.allclose(fwd, [0, 0, -1]) and np.allclose(right, [1, 0, 0])


def test_knee_hyperextension_is_clamped_forward():
    J = standing(knee_bend_deg=10, hyper=True)     # 膝が後ろへ反っている（過伸展）
    fwd, right, up = pelvis_frame(J)
    assert J[25][2] > 0                              # 膝が後ろ（+Z）にある
    fix = clamp_knee(J, 23, 25, 27, fwd)
    u = J[23] - J[25]; v = J[27] - J[25]
    ang = math.degrees(math.acos(np.dot(u, v) / np.linalg.norm(u) / np.linalg.norm(v)))
    assert fix > 0 and ang <= 177.01 and J[25][2] < 0          # 膝が前（-Z）へ移る
    assert abs(np.linalg.norm(J[25] - J[23]) - 0.45 * math.sqrt(1 + math.sin(math.radians(10)) ** 2)) < 1e-6   # 骨長は保たれる


def test_normal_knee_is_untouched():
    J = standing(knee_bend_deg=60)
    fwd, _, _ = pelvis_frame(J)
    assert clamp_knee(J, 23, 25, 27, fwd) == 0.0


def test_hip_range_clamp():
    J = standing()
    fwd, right, up = pelvis_frame(J)
    J[25] = J[23] + np.array([0, 0.4, -0.2])   # 大腿が上に上がりすぎ（屈曲 約153° > 130°）
    fix = clamp_hip(J, 23, 25, -1.0, fwd, right, up)
    t = J[25] - J[23]
    fl = math.degrees(math.atan2(np.dot(t, fwd), -np.dot(t, up)))
    assert fix > 0 and fl <= 130.01


def test_bone_length_normalization():
    J = standing(); med = {}
    for a, b in BONES + [(23, 24), (11, 12)]:
        med[(a, b)] = float(np.linalg.norm(J[b] - J[a]))
    med[("torso",)] = 0.5
    J2 = J.copy(); J2[27] = J2[25] + (J2[27] - J2[25]) * 1.5   # 下腿が 1.5 倍に伸びた検出
    out = normalize_bone_lengths(J2, med)
    assert abs(np.linalg.norm(out[27] - out[25]) - med[(25, 27)]) < 1e-6


def test_weak_perspective_fit_recovers_projection():
    J = standing(knee_bend_deg=30)
    A = np.array([[300.0, 0, 20], [0, -300.0, 10]]); b = np.array([640.0, 500.0])
    kp = [[*(A @ J[i] + b) / np.array([1280, 720]), 1.0] for i in range(33)]
    fit = fit_weak_perspective(J, kp, [1.0] * 33, 1280, 720)
    assert fit and fit[2] < 1e-6 and np.allclose(fit[0], A, atol=1e-6)


class Ctx:
    def __init__(self, frames, metrics, view, fps):
        self.scratch = {"frames": frames, "metrics": metrics, "view": view, "sample_fps": fps, "traj": [{"x": 100 + i, "y": 300} for i in range(len(frames))]}
        self.params = {"ski_length_m": 1.65}; self.model_versions = {}


def test_stage_outputs_boots_on_skis_and_flags():
    fps, n = 30, 12
    frames, metrics = [], []
    for i in range(n):
        J = standing(knee_bend_deg=40)
        world = [[p[0], -p[1], -p[2]] for p in J]          # BlazePose 形式へ戻す
        kp = [[0.5 + p[0] * 0.3, 0.5 - p[1] * 0.3, 1.0] for p in J]
        frames.append({"i": i, "t": i / fps, "worldS": world, "kpS": kp, "q": [1.0] * 33, "src": "det", "ski": None})
        metrics.append({"BH": 600.0, "facing": 1})
    data = {"decode": {"video": {"width": 1280, "height": 720}}, "perframe": {"camera": [{"cum_x": 0, "cum_y": 0, "resp": 0.5}] * n}, "camera": {"camera_moving": False}}
    out = Pose3DStage().run(Ctx(frames, metrics, "back", fps), data)
    p = out["pose3d"][5]
    assert p and p["conf"] > 0.5 and len(p["joints"]) == 33
    for key, ank in (("L", 27), ("R", 28)):
        s = p["ski"][key]
        # ブーツは足部の中心、板の中心はブーツの真下（地面）
        assert abs(s["boot"][0] - p["joints"][ank][0]) < 0.1 and abs(s["center"][1] - p["floor"]) < 1e-6
        assert abs(math.hypot(*s["dir"]) - 1) < 1e-3 and s["src"] == "foot+pelvis"
    assert "ski_cross" not in p["flags"] and out["summary"]["ski_cross_frames"] == 0
    assert p["root"] is not None and p["root_conf"] <= 0.5
