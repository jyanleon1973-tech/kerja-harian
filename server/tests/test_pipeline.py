"""パイプライン各段階の単体テスト（モデル不要の合成データ）。"""
from __future__ import annotations

import math

import numpy as np

from app.pipeline.metrics import compute_metrics, cog2d
from app.pipeline.pose import RTMPoseONNXBackend
from app.pipeline.temporal import fill_gaps, fix_left_right, joint_quality, one_euro_series, smooth_all
from app.pipeline.turns import _heading_rate, _median_filter


def make_kp(shift_x=0.0, swap=False, vis=1.0):
    """直立した人物の 33 点（正規化座標）。左は画像の左（背面撮影相当）。"""
    kp = [[0.5, 0.1, vis] for _ in range(33)]
    def put(i, x, y): kp[i] = [x + shift_x, y, vis]
    put(0, 0.5, 0.08); put(7, 0.48, 0.1); put(8, 0.52, 0.1)
    put(11, 0.44, 0.25); put(12, 0.56, 0.25); put(13, 0.40, 0.38); put(14, 0.60, 0.38); put(15, 0.38, 0.50); put(16, 0.62, 0.50)
    put(23, 0.46, 0.52); put(24, 0.54, 0.52); put(25, 0.455, 0.72); put(26, 0.545, 0.72); put(27, 0.45, 0.92); put(28, 0.55, 0.92)
    put(29, 0.445, 0.95); put(30, 0.555, 0.95); put(31, 0.455, 0.97); put(32, 0.545, 0.97)
    for i in (17, 19, 21): put(i, 0.37, 0.52)
    for i in (18, 20, 22): put(i, 0.63, 0.52)
    if swap:
        for a, b in ((23, 24), (25, 26), (27, 28), (29, 30), (31, 32)):
            kp[a], kp[b] = kp[b], kp[a]
    return kp


def frame(i, kp, src="det"):
    return {"i": i, "t": i / 30, "kp": kp, "world": [[p[0] - 0.5, p[1] - 0.5, 0.0] for p in kp] if kp else None, "src": src}


def test_fix_left_right_swaps_back():
    frames = [frame(0, make_kp()), frame(1, make_kp(swap=True)), frame(2, make_kp())]
    skis = [{"ski": None}, {"ski": {"L": {"conf": 0.9}, "R": {"conf": 0.1}, "shared": False}}, {"ski": None}]
    swaps = fix_left_right(frames, skis)
    assert swaps == 1
    assert frames[1]["kp"][27][0] < frames[1]["kp"][28][0]      # 左足首が左に戻る
    assert skis[1]["ski"]["L"]["conf"] == 0.1                    # 板の L/R も入れ替わる
    assert "lr_swapped_legs" in frames[1]["flags"]


def test_joint_quality_repairs_single_frame_spike():
    frames = [frame(0, make_kp()), frame(1, make_kp()), frame(2, make_kp())]
    frames[1]["kp"][15] = [0.9, 0.9, 1.0]   # 左手首だけ飛ぶ
    spikes = joint_quality(frames)
    assert spikes == 1
    assert abs(frames[1]["kp"][15][0] - 0.38) < 1e-6 and frames[1]["q"][15] <= 0.55


def test_fill_gaps_interpolates_short_gaps_only():
    frames = [frame(0, make_kp()), frame(1, None, None), frame(2, None, None), frame(3, make_kp(shift_x=0.03))]
    for f in frames: f["q"] = [1.0] * 33 if f["kp"] else None
    assert fill_gaps(frames, max_gap=2) == 2
    assert frames[1]["src"] == "interp" and abs(frames[1]["kp"][0][0] - (0.5 + 0.01)) < 1e-6
    assert frames[1]["q"][0] == 0.7
    long = [frame(0, make_kp())] + [frame(i, None, None) for i in range(1, 6)] + [frame(6, make_kp())]
    for f in long: f["q"] = [1.0] * 33 if f["kp"] else None
    assert fill_gaps(long, max_gap=2) == 0 and long[3]["src"] is None


def test_one_euro_preserves_fast_motion_and_removes_jitter():
    dt = 1 / 30
    t = np.arange(90) * dt
    step = np.where(t > 1.5, 1.0, 0.0)                    # 急な切り替え
    jitter = 0.02 * np.sin(2 * np.pi * 12 * t)           # 12 Hz の細かい揺れ
    out = np.array(one_euro_series(list(step + jitter), dt, 1.2, 2.0))
    assert out[60:].mean() > 0.9 and out[:40].mean() < 0.1       # 段差は残る
    assert abs(out[58] - 1.0) < 0.25                              # 段差の 0.4 s 後にはほぼ追従（遅れなし）
    assert np.std(out[10:40]) < np.std((step + jitter)[10:40]) * 0.6   # 揺れは減る


def test_smooth_all_keeps_raw_and_handles_gaps():
    frames = [frame(i, make_kp(shift_x=0.001 * i)) for i in range(10)]
    frames[4] = frame(4, None, None)
    for f in frames: f["q"] = [1.0] * 33 if f["kp"] else None
    smooth_all(frames, 1 / 30, 16 / 9)
    assert frames[4]["kpS"] is None and frames[5]["kpS"] is not None
    assert frames[0]["kp"] is not frames[0]["kpS"]


def test_compute_metrics_classification_by_view():
    f = {"kpS": make_kp(), "q": [1.0] * 33, "worldS": [[p[0] - 0.5, p[1] - 0.5, 0.0] for p in make_kp()], "ski": None, "src": "det"}
    back = compute_metrics(f, "back", 1, 1280, 720)
    assert back["M"]["shoulderTilt"]["cls"] == "obs" and abs(back["M"]["shoulderTilt"]["v"]) < 0.5
    assert back["M"]["trunkFwd"]["cls"] == "na" and back["M"]["skiOpen"]["cls"] == "na"   # 板は未検出なので不可
    assert back["M"]["stance"]["cls"] == "obs" and back["M"]["stance"]["v"] > 0
    assert back["M"]["lean"]["cls"] == "est"
    side = compute_metrics(f, "side", 0, 1280, 720)
    assert side["M"]["trunkFwd"]["cls"] == "obs" and side["M"]["shoulderTilt"]["cls"] == "na"
    assert side["M"]["kneeL"]["cls"] == "obs" and side["M"]["kneeL"]["v"] < 5     # 伸びている
    assert side["M"]["cogLat"]["cls"] == "na" and side["M"]["cogFwd"]["cls"] == "est"


def test_compute_metrics_hides_low_confidence_values():
    kp = make_kp(); q = [1.0] * 33; q[25] = 0.2
    f = {"kpS": kp, "q": q, "worldS": None, "ski": None, "src": "det"}
    m = compute_metrics(f, "side", 0, 1280, 720)
    assert m["M"]["kneeL"]["v"] is None and m["M"]["kneeL"].get("low") and m["M"]["kneeR"]["v"] is not None


def test_ski_metrics_only_when_detected():
    kp = make_kp()
    # 背面撮影: 画像左の左板は上端（遠く）が右へ、画像右の右板は上端が左へ → 先端が閉じるハの字
    ski = {"L": {"ang": math.radians(100), "conf": 0.8, "fx": 500, "fy": 690, "tip": 80, "tail": 60}, "R": {"ang": math.radians(80), "conf": 0.7, "fx": 700, "fy": 690, "tip": 80, "tail": 60}, "shared": False}
    f = {"kpS": kp, "q": [1.0] * 33, "worldS": None, "ski": ski, "src": "det"}
    m = compute_metrics(f, "back", -1, 1280, 720)
    assert m["M"]["skiAngL"]["cls"] == "obs" and m["M"]["skiOpen"]["cls"] == "obs" and m["M"]["skiOpen"]["v"] > 0  # 先端が閉じる → ハの字
    ski["R"]["conf"] = 0.3
    m2 = compute_metrics({**f, "ski": ski}, "back", -1, 1280, 720)
    assert m2["M"]["skiAngR"]["cls"] == "na" and m2["M"]["skiOpen"]["cls"] == "na"


def test_cog2d_is_inside_body():
    kp = make_kp(); x, y = cog2d(kp, 1000, 1000)
    assert 450 < x < 550 and 400 < y < 700


def test_heading_rate_sign_and_threshold():
    pts = [{"x": 100 * math.cos(a), "y": 100 * math.sin(a)} for a in np.linspace(0, math.pi, 30)]  # 画像座標で時計回り
    rate = _heading_rate(pts, 1 / 30, 3, 640)
    mid = [r for r in rate[5:-5] if r is not None]
    assert mid and all(r > 0 for r in mid)
    assert _median_filter([None, 1, 1, None], 1)[0] == 1


def test_simcc_decode():
    sx = np.zeros((2, 40)); sy = np.zeros((2, 60)); sx[0, 10] = 0.9; sy[0, 30] = 0.8; sx[1, 20] = 0.3; sy[1, 5] = 0.6
    xy, conf = RTMPoseONNXBackend.decode_simcc(sx, sy, 2.0)
    assert xy[0].tolist() == [5.0, 15.0] and abs(conf[0] - 0.8) < 1e-9 and abs(conf[1] - 0.3) < 1e-9
