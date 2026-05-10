from __future__ import annotations

import logging
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from inference.identity.face_quality import score_face_quality
from inference.identity.runtime_config import load_identity_config
from inference.identity_db import IdentityDB, get_db

logger = logging.getLogger(__name__)


def _normalize(values: list[float] | np.ndarray, dim: int = 512) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    if arr.size < dim:
        arr = np.pad(arr, (0, dim - arr.size))
    elif arr.size > dim:
        arr = arr[:dim]
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        raise RuntimeError("Zero-norm embedding cannot be enrolled.")
    return arr / norm


class IdentityEnrollmentEngine:
    """Multi-image face enrollment with per-image quality control."""

    def __init__(
        self,
        db: IdentityDB | None = None,
        store: Any | None = None,
        config: dict[str, Any] | None = None,
        face_analyzer: Any | None = None,
    ) -> None:
        from inference.identity.identity_profile_store import get_identity_store

        self._db = db or get_db()
        self._store = store or get_identity_store()
        self._cfg = config or load_identity_config()
        self._face_cfg = self._cfg.get("face", {})
        self._privacy_cfg = self._cfg.get("privacy", {})
        self._face_analyzer = face_analyzer or self._build_face_analyzer()
        self._image_dir = Path("storage/enrollments/images")
        self._image_dir.mkdir(parents=True, exist_ok=True)

    def _build_face_analyzer(self) -> Any | None:
        try:
            from inference.identity_fusion_engine import _FaceEmbedder

            embedder = _FaceEmbedder(self._face_cfg)
            return embedder if embedder.available else None
        except Exception as exc:
            logger.warning("Enrollment analyzer unavailable: %s", exc)
            return None

    def _analyze_image(self, image: np.ndarray) -> dict[str, Any] | None:
        if self._face_analyzer is None:
            return None
        if hasattr(self._face_analyzer, "analyze"):
            return self._face_analyzer.analyze(image)
        if callable(self._face_analyzer):
            return self._face_analyzer(image)
        return None

    @staticmethod
    def _decode_image(data: bytes) -> np.ndarray | None:
        array = np.frombuffer(data, dtype=np.uint8)
        if array.size == 0:
            return None
        try:
            import cv2

            imdecode = getattr(cv2, "imdecode", None)
            if callable(imdecode):
                decoded = imdecode(array, getattr(cv2, "IMREAD_COLOR", 1))
                if isinstance(decoded, np.ndarray) and decoded.size != 0:
                    return decoded
        except Exception:
            pass
        try:
            with Image.open(BytesIO(data)) as image:
                rgb = image.convert("RGB")
                return np.asarray(rgb)[:, :, ::-1].copy()
        except Exception:
            return None

    @staticmethod
    def _crop_face(image: np.ndarray, bbox: list[float] | None) -> np.ndarray:
        if not bbox or len(bbox) != 4:
            return image
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = image.shape[:2]
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return image
        return image[y1:y2, x1:x2].copy()

    def _aggregate_embeddings(self, embeddings: list[list[float]]) -> list[float]:
        matrix = np.stack([_normalize(embedding, int(self._face_cfg.get("embedding_dim", 512))) for embedding in embeddings], axis=0)
        centroid = np.mean(matrix, axis=0)
        distances = np.linalg.norm(matrix - centroid, axis=1)
        if len(embeddings) > 2:
            keep_mask = distances <= np.quantile(distances, 0.8)
            matrix = matrix[keep_mask]
        aggregate = np.mean(matrix, axis=0)
        return _normalize(aggregate, int(self._face_cfg.get("embedding_dim", 512))).astype(float).tolist()

    def _persist_image(self, identity_id: str, filename: str, data: bytes) -> str | None:
        if not bool(self._privacy_cfg.get("store_raw_faces", False)):
            return None
        safe_name = f"{identity_id}_{int(time.time() * 1000)}_{Path(filename).name}"
        target = (self._image_dir / safe_name).resolve()
        if not str(target).startswith(str(self._image_dir.resolve())):
            raise ValueError("Unsafe enrollment image path")
        target.write_bytes(data)
        return safe_name

    def enroll_person(
        self,
        images: list[dict[str, Any]],
        *,
        identity_id: str | None = None,
        display_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        profile = self._store.get_identity(identity_id) if identity_id else None
        if profile is None:
            profile = self._store.create_identity(display_name=display_name, metadata=metadata)
        identity_id = profile.identity_id

        accepted_embeddings: list[list[float]] = []
        accepted_quality_scores: list[float] = []
        rejected: list[dict[str, Any]] = []
        accepted = 0

        batch_id = str(uuid.uuid4())
        batch_metadata = {
            "operator_review_required": True,
            "source": "face_enrollment",
            **metadata,
        }

        for image in images:
            filename = str(image.get("filename") or "upload.jpg")
            data = image.get("data") or b""
            decoded = self._decode_image(data)
            if decoded is None:
                rejected.append({"filename": filename, "reasons": ["image_decode_failed"]})
                self._store.add_face_enrollment(
                    identity_id=identity_id,
                    image_path=None,
                    quality_score=0.0,
                    status="rejected",
                    rejection_reasons=["image_decode_failed"],
                    quality_metrics={},
                    metadata={"filename": filename, **batch_metadata},
                    batch_enrollment_id=batch_id,
                )
                continue
            analysis = self._analyze_image(decoded)
            if not analysis:
                rejected.append({"filename": filename, "reasons": ["no_face_detected"]})
                self._store.add_face_enrollment(
                    identity_id=identity_id,
                    image_path=None,
                    quality_score=0.0,
                    status="rejected",
                    rejection_reasons=["no_face_detected"],
                    quality_metrics={},
                    metadata={"filename": filename, **batch_metadata},
                    batch_enrollment_id=batch_id,
                )
                continue
            face_crop = self._crop_face(decoded, analysis.get("bbox"))
            quality = score_face_quality(
                face_crop,
                detection_score=analysis.get("detection_score"),
                pose=analysis.get("pose"),
                embedding=analysis.get("embedding"),
                min_face_size_px=int(self._face_cfg.get("min_face_size_px", 40)),
                min_detection_score=float(self._face_cfg.get("min_detection_score", 0.60)),
                min_quality_score=float(self._face_cfg.get("min_quality_score", 0.55)),
            )
            if not quality["is_usable"]:
                rejected.append({"filename": filename, "reasons": quality["reasons"], "quality": quality})
                self._store.add_face_enrollment(
                    identity_id=identity_id,
                    image_path=None,
                    quality_score=float(quality["quality_score"]),
                    status="rejected",
                    rejection_reasons=list(quality["reasons"]),
                    quality_metrics=dict(quality["metrics"]),
                    source_breakdown={"face": float(analysis.get("detection_score", 0.0))},
                    metadata={"filename": filename, **batch_metadata},
                    batch_enrollment_id=batch_id,
                )
                continue

            accepted += 1
            embedding = list(analysis.get("embedding") or [])
            accepted_embeddings.append(embedding)
            accepted_quality_scores.append(float(quality["quality_score"]))
            image_path = self._persist_image(identity_id, filename, data)
            self._store.add_face_enrollment(
                identity_id=identity_id,
                image_path=image_path,
                embedding=embedding,
                quality_score=float(quality["quality_score"]),
                status="accepted",
                rejection_reasons=[],
                quality_metrics=dict(quality["metrics"]),
                source_breakdown={"face": float(analysis.get("detection_score", 0.0))},
                metadata={"filename": filename, **batch_metadata},
                batch_enrollment_id=batch_id,
            )

        aggregated_embedding = self._aggregate_embeddings(accepted_embeddings) if accepted_embeddings else None
        batch_ref = f"emb:{identity_id}:{int(time.time())}" if aggregated_embedding else None
        enrollment_profile = self._store.create_enrollment_profile(
            identity_id=identity_id,
            enrollment_id=batch_id,
            display_name=display_name or profile.display_name,
            status="completed" if aggregated_embedding else "rejected",
            total_images=len(images),
            accepted_images=accepted,
            rejected_images=len(images) - accepted,
            aggregate_method="mean_cluster_trimmed",
            aggregate_embedding_ref=batch_ref,
            quality_summary={
                "accepted_quality_avg": round(sum(accepted_quality_scores) / len(accepted_quality_scores), 4) if accepted_quality_scores else 0.0,
                "rejected_count": len(rejected),
                "rejection_reasons": [item["reasons"] for item in rejected],
            },
            metadata={
                "identity_id": identity_id,
                "batch_enrollment_id": batch_id,
                "display_name": display_name,
                "rejected": rejected,
                **batch_metadata,
            },
        )

        if aggregated_embedding:
            self._db.persist_identity(
                identity_id=identity_id,
                face_embedding=aggregated_embedding,
                metadata={
                    "enrollment_id": enrollment_profile.enrollment_id,
                    "display_name": display_name or profile.display_name,
                    "source": "multi_image_enrollment",
                },
            )

        return {
            "status": "ok" if aggregated_embedding else "error",
            "identity_id": identity_id,
            "enrollment_id": enrollment_profile.enrollment_id,
            "accepted_images": accepted,
            "rejected_images": len(images) - accepted,
            "rejected": rejected,
            "item": enrollment_profile.to_public_dict(),
        }
