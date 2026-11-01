"""パイプラインの組み立てと結果の保存。"""
from __future__ import annotations

from typing import Any

from .base import PIPELINE_VERSION, Context, run_stages
from .camera import CameraStage
from .decode import DecodeStage
from .metrics import MetricsStage
from .perframe import PerFrameStage
from .temporal import TemporalStage
from .turns import TurnStage
from .vectors import VectorStage
from .pose3d import Pose3DStage
from .track import TrackStage


class ConfidenceStage:
    """コマごとの総合信頼度と、ジョブ全体の品質要約（誤差の発生段階を追えるように段階別の数値を集約）。"""
    name = "confidence"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]; metrics = ctx.scratch["metrics"]; turn = ctx.scratch["turn"]
        per = []
        for f, m, t in zip(frames, metrics, turn):
            if not f.get("q"):
                per.append({"overall": 0.0, "reason": "undetected"}); continue
            core = [f["q"][j] for j in (11, 12, 23, 24, 25, 26, 27, 28)]
            score = sum(core) / len(core) * (0.7 if f.get("src") == "interp" else 1.0)
            per.append({"overall": round(score, 3), "src": f.get("src"), "turn_known": t is not None, "flags": f.get("flags", [])})
        det = sum(1 for f in frames if f.get("src") == "det"); n = max(1, len(frames))
        summary = {
            "detect_rate": round(det / n, 3), "interp_rate": round(sum(1 for f in frames if f.get("src") == "interp") / n, 3),
            "missing_rate": round(sum(1 for f in frames if not f.get("src")) / n, 3),
            "mean_core_conf": round(sum(p["overall"] for p in per) / n, 3),
            "lr_swaps": data["temporal"]["summary"]["lr_swaps"], "spikes": data["temporal"]["summary"]["spikes"],
            "ski_detect_rate_L": round(data["perframe"]["summary"]["ski_detected_L"] / n, 3), "ski_detect_rate_R": round(data["perframe"]["summary"]["ski_detected_R"] / n, 3),
            "turn_unknown_rate": round(sum(1 for t in turn if t is None) / n, 3), "camera_moving": data["camera"]["camera_moving"], "view": data["camera"]["view"],
            "vfr_suspected": data["decode"]["video"].get("vfr_suspected"),
        }
        warnings = []
        if summary["detect_rate"] < 0.5: warnings.append("検出率が低い（選手が小さい・隠れが多い）")
        if summary["camera_moving"]: warnings.append("カメラが大きく動いている。位置系の指標の信頼度が下がる")
        if data["camera"]["view"] == "oblique": warnings.append("斜めからの撮影。左右方向の 2D 指標は推定扱い")
        if summary["vfr_suspected"]: warnings.append("可変フレームレートの疑い。コマの時刻は実タイムスタンプに基づく")
        return {"per_frame": per, "summary": summary, "warnings": warnings}


class ResultStage:
    name = "results"

    def run(self, ctx, data):
        frames = ctx.scratch["frames"]; metrics = ctx.scratch["metrics"]; turn = ctx.scratch["turn"]; phase = ctx.scratch["phase"]
        conf = data["confidence"]["per_frame"]
        vec = data["vectors"]["vectors"]; ind = data["vectors"]["indicators"]; tend = data["vectors"]["tendency"]; p3 = data["pose3d"]["pose3d"]
        tr = data["track"]["tracks"]; camd = data["track"]["camera_default"]
        out_frames = []
        for k, f in enumerate(frames):
            out_frames.append({
                "vec": vec[k], "ind": ind[k], "tend": tend[k], "p3": p3[k], "track": tr[k], "cam": camd[k],
                "i": f["i"], "t": f["t"], "src": f.get("src"), "flags": f.get("flags", []),
                "lm": f.get("kpS"), "lmRaw": f.get("kp"), "world": f.get("worldS"), "q": f.get("q"), "ski": f.get("ski"),
                "turn": turn[k], "phase": phase[k], "metrics": metrics[k]["M"] if metrics[k] else None,
                "geom": ({"cog2": metrics[k]["cog2"], "feet2": metrics[k]["feet2"], "BH": metrics[k]["BH"]} if metrics[k] else None),
                "confidence": conf[k]["overall"],
            })
        result = {
            "schema": "ski-analysis/2", "pipeline_version": PIPELINE_VERSION, "model_versions": ctx.model_versions,
            "params": ctx.params, "video": data["decode"]["video"], "sample_fps": ctx.scratch["sample_fps"],
            "keypoint_format": data["perframe"]["keypoint_format"], "view": data["camera"]["view"], "view_auto": data["camera"]["view_auto"],
            "camera": {"moving": data["camera"]["camera_moving"], "total_shift_ratio": data["camera"]["total_shift_ratio"]},
            "segments": ctx.scratch["segments"], "switches": data["turns"]["switches"], "vector_modes": data["vectors"]["modes"], "follow": {"settings_default": data["track"]["settings_default"], "summary": data["track"]["summary"]}, "pose3d": {"axes": data["pose3d"]["axes"], "ski_length_m": data["pose3d"]["ski_length_m"], "summary": data["pose3d"]["summary"]},
            "quality": data["confidence"]["summary"], "warnings": data["confidence"]["warnings"],
            "frames": out_frames,
        }
        key = f"jobs/{ctx.job_id}/results.json"
        ctx.storage.put_json(key, result)
        ctx.scratch["result_key"] = key
        return {"result_key": key, "summary": {"frames": len(out_frames)}}


def build_stages():
    return [DecodeStage(), PerFrameStage(), TemporalStage(), CameraStage(), TurnStage(), MetricsStage(), VectorStage(), Pose3DStage(), TrackStage(), ConfidenceStage(), ResultStage()]


def run_job(ctx: Context, on_stage_done=None) -> dict[str, Any]:
    data = run_stages(ctx, build_stages(), on_stage_done)
    return {"result_key": ctx.scratch["result_key"], "model_versions": ctx.model_versions, "quality": data["confidence"]["summary"]}
