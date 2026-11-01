"""運動ベクトル段階のテスト（合成データ）。"""
from app.pipeline.vectors import VectorStage
from tests.test_pipeline import make_kp


class Ctx:
    def __init__(self, frames, metrics, turn, phase, view, fps):
        self.scratch = {"frames": frames, "metrics": metrics, "turn": turn, "phase": phase, "view": view, "sample_fps": fps}


def test_cog_motion_vector_direction_and_labels():
    n, fps = 30, 30
    frames, metrics = [], []
    for i in range(n):
        kp = make_kp(shift_x=0.01 * i)          # 画像の右へ等速移動
        frames.append({"i": i, "t": i / fps, "kpS": kp, "q": [1.0] * 33, "src": "det"})
        metrics.append({"cog2": [500 + 10 * i, 400], "feet2": [500 + 10 * i, 900], "BH": 800,
                        "M": {"kneeL": {"v": 20}, "kneeR": {"v": 40}, "hipHeight": {"v": 70}, "cogFwd": {"v": None}, "cogLat": {"v": 1.0}, "skiOpen": {"v": None}}})
    cam = [{"i": i, "dx": 0, "dy": 0, "cum_x": 0, "cum_y": 0, "resp": 0.5} for i in range(n)]
    data = {"perframe": {"camera": cam}, "camera": {"camera_moving": False}, "decode": {"video": {"width": 1000, "height": 1000}}}
    out = VectorStage().run(Ctx(frames, metrics, [1] * n, [1] * n, "back", fps), data)
    v = out["vectors"][15]
    assert v["mode"] == "A" and abs(v["dir_deg"]) < 5 and abs(v["mag_bh_s"] - (10 * fps / 800)) < 0.05   # 右向き、0.375 身長/秒
    assert v["conf"] > 0.9 and "推定" in v["label"]
    ind = out["indicators"][15]
    assert ind["knee_out"] == 20 and ind["knee_in"] == 40          # 右ターン → 外脚 = 左
    assert ind["note"].startswith("身体運動指標")
    t = out["tendency"][15]
    assert t and t["validated"] is False and abs(t["L"] + t["R"] - 1) < 1e-6 and t["conf"] <= 0.5
    assert out["modes"]["C"]["available"] is False and out["modes"]["B"]["status"] == "reference_only_unvalidated"


def test_camera_motion_is_subtracted():
    n, fps = 20, 30
    frames = [{"i": i, "t": i / fps, "kpS": make_kp(), "q": [1.0] * 33, "src": "det"} for i in range(n)]
    metrics = [{"cog2": [500, 400], "feet2": [500, 900], "BH": 800, "M": {"kneeL": {"v": 20}, "kneeR": {"v": 40}, "hipHeight": {"v": 70}, "cogFwd": {"v": None}, "cogLat": {"v": 0}, "skiOpen": {"v": None}}} for _ in range(n)]
    # 選手は画面上で静止、カメラが左へパン（背景が右へ流れる → cum_x が増える）: 選手は実際には右へ動いている
    cam = [{"i": i, "dx": 8, "dy": 0, "cum_x": 8 * i, "cum_y": 0, "resp": 0.5} for i in range(n)]
    data = {"perframe": {"camera": cam}, "camera": {"camera_moving": True}, "decode": {"video": {"width": 1000, "height": 1000}}}
    out = VectorStage().run(Ctx(frames, metrics, [0] * n, [None] * n, "side", fps), data)
    v = out["vectors"][10]
    assert v["dx"] > 100 and v["apparent_only"] is True and v["conf"] < 0.9
    assert out["indicators"][10]["cog_to_ankleL_pct"] is None   # 側面では横方向の指標を出さない
