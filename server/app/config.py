"""設定。環境変数で上書きできる。GPU クラウドへの接続情報はここに集約し、承認後に設定する。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("SKI_DATA_DIR", "./data")).resolve())
    db_path: Path | None = None
    model_dir: Path = field(default_factory=lambda: Path(os.environ.get("SKI_MODEL_DIR", "./models")).resolve())
    # アップロード制限
    max_upload_mb: int = int(os.environ.get("SKI_MAX_UPLOAD_MB", "500"))
    allowed_video_types: tuple[str, ...] = ("video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "application/octet-stream")
    allowed_extensions: tuple[str, ...] = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
    # ジョブ
    max_concurrent_jobs: int = int(os.environ.get("SKI_MAX_CONCURRENT_JOBS", "1"))
    job_timeout_s: int = int(os.environ.get("SKI_JOB_TIMEOUT_S", "1800"))
    job_max_attempts: int = int(os.environ.get("SKI_JOB_MAX_ATTEMPTS", "2"))
    retention_days: int = int(os.environ.get("SKI_RETENTION_DAYS", "30"))
    # 解析の既定値
    pose_backend: str = os.environ.get("SKI_POSE_BACKEND", "mediapipe")   # mediapipe | rtmpose(未検証)
    pose_model: str = os.environ.get("SKI_POSE_MODEL", "heavy")           # mediapipe: lite | full | heavy
    default_fps: float = float(os.environ.get("SKI_DEFAULT_FPS", "30"))
    # ワーカー方式: inline（同一プロセスのスレッド）| external（GPU ワーカーがキューを取りに来る。Phase 2 では inline のみ実装）
    worker_mode: str = os.environ.get("SKI_WORKER_MODE", "inline")

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = self.data_dir / "ski.sqlite3"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings(**overrides) -> Settings:
    """テスト用: 設定を作り直す。"""
    global _settings
    _settings = Settings(**overrides)
    return _settings
