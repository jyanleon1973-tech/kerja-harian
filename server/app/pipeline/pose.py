"""姿勢推定バックエンド。
- MediaPipePoseBackend: CPU で動く既定（BlazePose GHUM 33 点、2D + 3D world）。回帰テストとフォールバック用。
- RTMPoseONNXBackend: GPU サーバー用（onnxruntime、SimCC 出力）。この環境ではモデルがなく未検証。
出力は共通形式: {"kp": [[x, y, score], ...] (画像の正規化座標), "world": [[x,y,z],...] or None, "format": "blazepose33"|"halpe26"|"coco17"}"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

MEDIAPIPE_URLS = {
    "lite": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}


def ensure_mediapipe_model(model_dir: str, variant: str) -> Path:
    p = Path(model_dir) / f"pose_landmarker_{variant}.task"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MEDIAPIPE_URLS[variant], p)  # 注意: 'latest' は更新で結果が変わりうる。本番では固定版を同梱する
    return p


class PoseBackend:
    name = "base"
    version = "0"
    keypoint_format = "blazepose33"

    def detect(self, rgb: np.ndarray) -> dict[str, Any] | None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class MediaPipePoseBackend(PoseBackend):
    name = "mediapipe_pose_landmarker"
    keypoint_format = "blazepose33"

    def __init__(self, model_dir: str, variant: str = "heavy", min_conf: float = 0.3):
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision

        self._mp = mp
        path = ensure_mediapipe_model(model_dir, variant)
        opts = vision.PoseLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.IMAGE, num_poses=1,
            min_pose_detection_confidence=min_conf, min_pose_presence_confidence=min_conf, min_tracking_confidence=min_conf)
        self._lm = vision.PoseLandmarker.create_from_options(opts)
        self.version = f"mediapipe=={mp.__version__}; model=pose_landmarker_{variant}(latest, size={path.stat().st_size})"

    def detect(self, rgb):
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = self._lm.detect(img)
        if not res.pose_landmarks:
            return None
        kp = [[p.x, p.y, float(p.visibility if p.visibility is not None else 1.0)] for p in res.pose_landmarks[0]]
        world = [[p.x, p.y, p.z] for p in res.pose_world_landmarks[0]] if res.pose_world_landmarks else None
        return {"kp": kp, "world": world, "format": self.keypoint_format}

    def close(self):
        try:
            self._lm.close()
        except Exception:
            pass


class RTMPoseONNXBackend(PoseBackend):
    """RTMPose（SimCC）の ONNX をそのまま動かすための雛形。
    入力: 切り出し済み人物画像。出力: SimCC の x/y 分布 → argmax/ピーク幅から座標と信頼度。
    モデル・前処理定数は mmpose/rtmpose の設定に合わせる。モデルがないため未検証。"""

    name = "rtmpose_onnx"
    keypoint_format = "halpe26"

    def __init__(self, onnx_path: str, input_size=(192, 256), simcc_split_ratio: float = 2.0, providers=None):
        import onnxruntime as ort  # type: ignore

        self.sess = ort.InferenceSession(onnx_path, providers=providers or ["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        self.input_size = input_size
        self.ratio = simcc_split_ratio
        self.mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
        self.std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
        self.version = f"rtmpose_onnx:{os.path.basename(onnx_path)}"

    @staticmethod
    def decode_simcc(simcc_x: np.ndarray, simcc_y: np.ndarray, ratio: float) -> tuple[np.ndarray, np.ndarray]:
        """SimCC 分布から (K,2) 座標と (K,) 信頼度。"""
        x_idx = simcc_x.argmax(axis=-1); y_idx = simcc_y.argmax(axis=-1)
        conf = np.minimum(simcc_x.max(axis=-1), simcc_y.max(axis=-1))
        return np.stack([x_idx / ratio, y_idx / ratio], axis=-1), conf

    def detect(self, rgb):
        import cv2
        h, w = rgb.shape[:2]
        iw, ih = self.input_size
        img = cv2.resize(rgb, (iw, ih)).astype(np.float32)
        img = (img - self.mean) / self.std
        inp = img.transpose(2, 0, 1)[None]
        sx, sy = self.sess.run(None, {self.input_name: inp})
        xy, conf = self.decode_simcc(sx[0], sy[0], self.ratio)
        kp = [[float(x / iw), float(y / ih), float(c)] for (x, y), c in zip(xy, conf)]
        return {"kp": kp, "world": None, "format": self.keypoint_format}


def make_backend(kind: str, model_dir: str, **kw) -> PoseBackend:
    if kind == "mediapipe":
        return MediaPipePoseBackend(model_dir, variant=kw.get("variant", "heavy"), min_conf=kw.get("min_conf", 0.3))
    if kind == "rtmpose":
        return RTMPoseONNXBackend(kw["onnx_path"])
    raise ValueError(f"unknown pose backend: {kind}")
