"""パイプラインの共通部品。各段階（Stage）は入力辞書を受け取り出力辞書を返す。
段階ごとの出力は JSON としてストレージに保存し、どの段階で誤差が生じたか後から追跡できるようにする。"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

PIPELINE_VERSION = "2.0.0"


class Canceled(Exception):
    pass


@dataclass
class Context:
    job_id: str
    params: dict[str, Any]
    storage: Any
    video_path: str
    model_dir: str
    progress: Callable[[float, str, str], None]   # (0-1, stage, message)
    should_cancel: Callable[[], bool] = lambda: False
    model_versions: dict[str, str] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)   # 段階間で受け渡す大きなデータ（保存しない）

    def check_cancel(self) -> None:
        if self.should_cancel():
            raise Canceled()


class Stage(Protocol):
    name: str
    def run(self, ctx: Context, data: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class StageRecord:
    seq: int
    stage: str
    key: str
    duration_ms: float
    summary: dict[str, Any]


def run_stages(ctx: Context, stages: list[Stage], on_stage_done: Callable[[StageRecord], None] | None = None) -> dict[str, Any]:
    """段階を順に実行。各段階の出力を jobs/<id>/stages/NN_<name>.json に保存する。"""
    data: dict[str, Any] = {}
    n = len(stages)
    for i, st in enumerate(stages):
        ctx.check_cancel()
        ctx.progress(i / n, st.name, f"{st.name} 開始")
        t0 = time.perf_counter()
        try:
            out = st.run(ctx, data)
        except Canceled:
            raise
        except Exception as e:  # 段階名付きで失敗を記録
            raise RuntimeError(f"stage '{st.name}' failed: {e}\n{traceback.format_exc()}") from e
        dur = (time.perf_counter() - t0) * 1000
        data[st.name] = out
        key = f"jobs/{ctx.job_id}/stages/{i + 1:02d}_{st.name}.json"
        summary = out.get("summary", {}) if isinstance(out, dict) else {}
        try:
            ctx.storage.put_json(key, out)
        except TypeError:
            ctx.storage.put_json(key, {"summary": summary, "note": "non-serializable payload omitted"})
        if on_stage_done:
            on_stage_done(StageRecord(i + 1, st.name, key, dur, summary))
    ctx.progress(1.0, "done", "完了")
    return data
