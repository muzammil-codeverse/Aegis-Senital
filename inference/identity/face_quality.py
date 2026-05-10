from __future__ import annotations

import math
from typing import Any

import numpy as np


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_pose_score(pose: Any) -> float | None:
    if pose is None:
        return None
    if isinstance(pose, (list, tuple, np.ndarray)) and len(pose) >= 3:
        yaw, pitch, roll = [abs(float(v)) for v in pose[:3]]
        total = yaw + pitch + 0.5 * roll
        return _clip01(1.0 - total / 90.0)
    return None


def _grayscale(face_image: np.ndarray) -> np.ndarray:
    if face_image.ndim == 2:
        return face_image.astype(np.float32)
    if face_image.ndim == 3:
        channels = face_image[..., :3].astype(np.float32)
        return np.mean(channels, axis=2)
    raise ValueError("Unsupported face image rank")


def _laplacian_variance(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    center = gray[1:-1, 1:-1]
    laplacian = (
        gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
        - 4.0 * center
    )
    return float(np.var(laplacian))


def score_face_quality(
    face_image: np.ndarray | None,
    *,
    detection_score: float | None = None,
    pose: Any = None,
    embedding: list[float] | np.ndarray | None = None,
    min_face_size_px: int = 40,
    min_detection_score: float = 0.60,
    min_quality_score: float = 0.55,
) -> dict[str, Any]:
    if face_image is None or face_image.size == 0:
        return {
            "quality_score": 0.0,
            "is_usable": False,
            "reasons": ["empty_face_crop"],
            "metrics": {},
        }

    height, width = face_image.shape[:2]
    gray = _grayscale(face_image)

    blur_score = _laplacian_variance(gray)
    brightness = float(np.mean(gray) / 255.0)
    dark_fraction = float(np.mean(gray < 20))
    bright_fraction = float(np.mean(gray > 245))
    occlusion_proxy = _clip01(1.0 - min(1.0, dark_fraction + bright_fraction))

    pose_score = _normalize_pose_score(pose)
    embedding_norm = float(np.linalg.norm(np.asarray(embedding, dtype=np.float32))) if embedding is not None else None

    size_score = _clip01(min(width, height) / max(float(min_face_size_px * 2), 1.0))
    blur_norm = _clip01(blur_score / 160.0)
    brightness_score = _clip01(1.0 - abs(brightness - 0.55) / 0.45)
    detection_norm = _clip01(float(detection_score if detection_score is not None else 0.0))
    embedding_score = 1.0
    if embedding_norm is not None:
        embedding_score = _clip01(1.0 - min(1.0, abs(embedding_norm - 1.0)))

    weights = {
        "size": 0.18,
        "blur": 0.18,
        "brightness": 0.14,
        "occlusion": 0.12,
        "detection": 0.20,
        "embedding": 0.08,
        "pose": 0.10 if pose_score is not None else 0.0,
    }
    total_weight = sum(weights.values())
    raw_score = (
        weights["size"] * size_score
        + weights["blur"] * blur_norm
        + weights["brightness"] * brightness_score
        + weights["occlusion"] * occlusion_proxy
        + weights["detection"] * detection_norm
        + weights["embedding"] * embedding_score
        + weights["pose"] * (pose_score if pose_score is not None else 0.0)
    )
    quality_score = round(raw_score / max(total_weight, 1e-6), 4)

    reasons: list[str] = []
    if width < min_face_size_px or height < min_face_size_px:
        reasons.append("face_too_small")
    if detection_score is not None and float(detection_score) < min_detection_score:
        reasons.append("low_detection_confidence")
    if blur_score < 18.0:
        reasons.append("face_too_blurry")
    if brightness < 0.12:
        reasons.append("underexposed")
    if brightness > 0.92:
        reasons.append("overexposed")
    if occlusion_proxy < 0.45:
        reasons.append("occlusion_proxy_high")
    if pose_score is not None and pose_score < 0.35:
        reasons.append("extreme_pose")
    if embedding_norm is not None and (math.isclose(embedding_norm, 0.0) or embedding_norm < 0.5):
        reasons.append("embedding_norm_invalid")
    if quality_score < min_quality_score:
        reasons.append("quality_below_threshold")

    return {
        "quality_score": quality_score,
        "is_usable": len(reasons) == 0,
        "reasons": reasons,
        "metrics": {
            "face_width": int(width),
            "face_height": int(height),
            "blur_score": round(blur_score, 3),
            "brightness": round(brightness, 4),
            "detection_score": round(float(detection_score or 0.0), 4),
            "occlusion_proxy": round(occlusion_proxy, 4),
            "pose_score": round(pose_score, 4) if pose_score is not None else None,
            "embedding_norm": round(embedding_norm, 4) if embedding_norm is not None else None,
        },
    }
