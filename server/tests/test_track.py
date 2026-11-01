"""追跡データとカメラ軌道のテスト。"""
import math

from app.pipeline.track import MAX_ZOOM, plan_camera, track_frame
from tests.test_pipeline import make_kp


def tf(shift_x=0.0, scale=1.0, src="det", ski=None, q=1.0):
    kp = [[0.5 + (p[0] - 0.5) * scale + shift_x, 0.5 + (p[1] - 0.5) * scale, 1.0] for p in make_kp()]
    return {"kpS": kp, "q": [q] * 33, "src": src, "ski": ski}


def test_track_frame_regions_include_skis():
    ski = {"L": {"ang": 0.0, "conf": 0.9, "fx": 400, "fy": 950, "tip": 300, "tail": 300}, "R": None, "shared": False}
    t = track_frame(tf(ski=ski), 1000, 1000)
    assert t["track_id"] == 1 and t["state"] == "det" and 0.4 < t["center"][0] < 0.6
    assert t["full"][0] <= 0.1 and t["full"][2] >= 0.7          # 板の両端まで含む
    assert t["body"][0] > t["full"][0] and t["skis"][3] >= 0.95
    assert track_frame({"kpS": None, "q": None}, 1000, 1000) is None


def test_plan_camera_centers_and_zooms():
    n, dt = 60, 1 / 30
    tracks = [track_frame(tf(shift_x=-0.3 + 0.6 * i / (n - 1), scale=0.5), 1280, 720) for i in range(n)]   # 左から右へ移動、小さく映る
    cam = plan_camera(tracks, dt, 1280, 720, {"mode": "zoom", "framing": "full", "target_frac": 0.75, "smooth": 0.5})
    assert len(cam) == n and all(c["state"] == "tracking" for c in cam)
    assert cam[5]["cx"] < cam[n - 6]["cx"]                       # 選手を追って移動
    assert all(1.0 <= c["zoom"] <= MAX_ZOOM for c in cam) and cam[30]["zoom"] > 1.3   # 小さい選手は拡大
    for c in cam:                                                 # 切り抜きは画面内
        assert c["cx"] - c["w"] / 2 >= -1e-6 and c["cx"] + c["w"] / 2 <= 1 + 1e-6 and c["cy"] - c["h"] / 2 >= -1e-6
    # 急な移動の抑制: 隣接コマの中心移動は 0.6 画面幅/秒 以下
    assert max(abs(cam[i + 1]["cx"] - cam[i]["cx"]) for i in range(n - 1)) <= 0.6 * dt + 1e-9
    # 追尾のみ（ズームなし）
    cam2 = plan_camera(tracks, dt, 1280, 720, {"mode": "follow"})
    assert all(abs(c["zoom"] - 1.0) < 1e-9 for c in cam2)
    assert all(c["zoom"] == 1.0 and c["cx"] == 0.5 for c in plan_camera(tracks, dt, 1280, 720, {"mode": "normal"}))


def test_plan_camera_hold_then_return_on_loss():
    dt = 1 / 30
    tracks = [track_frame(tf(shift_x=-0.3, scale=0.4), 1280, 720)] * 20 + [None] * 90
    cam = plan_camera(tracks, dt, 1280, 720, {"mode": "zoom"})
    assert cam[25]["state"] == "hold" and abs(cam[25]["cx"] - cam[19]["cx"]) < 1e-6 and cam[25]["zoom"] == cam[19]["zoom"]
    assert cam[60]["state"] == "lost" and cam[109]["zoom"] < cam[19]["zoom"] and abs(cam[109]["cx"] - 0.5) < abs(cam[19]["cx"] - 0.5)


def test_plan_camera_lowres_flag_and_max_zoom():
    dt = 1 / 30
    tracks = [track_frame(tf(scale=0.08), 640, 360)] * 10          # 非常に小さい選手、低解像度の元動画
    cam = plan_camera(tracks, dt, 640, 360, {"mode": "zoom", "max_zoom": 3.0})
    assert all(c["zoom"] <= 3.0 for c in cam) and cam[-1]["lowres"] is True
