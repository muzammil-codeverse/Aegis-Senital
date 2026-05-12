from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from inference.identity.face_quality import score_face_quality
from inference.identity.runtime_config import load_identity_config
from inference.identity_db import IdentityDB, get_db
from inference.schemas import Detection, FramePacket, Track
from ml.runtime import ModelRouter, system_boot_check

logger = logging.getLogger(__name__)

_TEMP_PREFIX = "TEMP_"
_HISTORY_LEN = 5


def _normalize(values: list[float] | np.ndarray | None, dim: int = 512) -> np.ndarray:
    if values is None:
        raise RuntimeError("Identity embedding missing - system cannot operate safely")
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        raise RuntimeError("Identity embedding missing - system cannot operate safely")
    if arr.size < dim:
        arr = np.pad(arr, (0, dim - arr.size))
    elif arr.size > dim:
        arr = arr[:dim]
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        raise RuntimeError("Zero-norm identity embedding detected - dummy embeddings are not permitted")
    return arr / norm


def _cosine_similarity(left: list[float] | np.ndarray | None, right: list[float] | np.ndarray | None, dim: int = 512) -> float:
    if left is None or right is None or len(left) == 0 or len(right) == 0:
        return 0.0
    lhs = _normalize(left, dim)
    rhs = _normalize(right, dim)
    denom = float(np.linalg.norm(lhs) * np.linalg.norm(rhs))
    if denom == 0.0:
        return 0.0
    return float(np.dot(lhs, rhs))


class _FaceEmbedder:
    def __init__(self, config: dict[str, Any]) -> None:
        self._cfg = config
        self._app = None
        self._available = False
        self.backend = str(config.get("provider", "insightface"))
        self._last_error: str | None = None
        if not bool(config.get("enabled", True)):
            return
        try:
            system_boot_check()
            from insightface.app import FaceAnalysis
            import torch

            model_meta = ModelRouter().get_model("face")
            model_path = Path(model_meta["resolved_path"])
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if str(config.get("device", "cuda")).lower() == "cuda" and torch.cuda.is_available()
                else ["CPUExecutionProvider"]
            )
            ctx_id = 0 if providers[0] == "CUDAExecutionProvider" else -1
            detection_size = tuple(config.get("detection_size", [640, 640]))
            self._app = FaceAnalysis(
                name=model_path.name,
                root=str(model_path.parent.parent),
                providers=providers,
            )
            self._app.prepare(ctx_id=ctx_id, det_size=detection_size)
            self._available = True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("_FaceEmbedder unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def analyze(self, image: np.ndarray | None) -> dict[str, Any] | None:
        if not self._available or self._app is None or image is None or image.size == 0:
            return None
        try:
            faces = self._app.get(image)
            if not faces:
                return None
            face = max(
                faces,
                key=lambda item: float((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])),
            )
            return {
                "embedding": _normalize(face.normed_embedding, int(self._cfg.get("embedding_dim", 512))).astype(float).tolist(),
                "detection_score": float(getattr(face, "det_score", 0.0)),
                "pose": list(getattr(face, "pose", [])) if getattr(face, "pose", None) is not None else None,
                "bbox": [float(v) for v in getattr(face, "bbox", [])],
            }
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("_FaceEmbedder.analyze failed: %s", exc)
            return None


class _AppearanceEmbedder:
    def __init__(self, config: dict[str, Any]) -> None:
        self._cfg = config
        self._extractor = None
        self._available = False
        self.backend = str(config.get("provider", "osnet"))
        self._last_error: str | None = None
        if not bool(config.get("enabled", True)):
            return
        try:
            system_boot_check()
            import torch
            from torchreid.reid.utils import FeatureExtractor

            use_cuda = str(config.get("device", "cuda")).lower() == "cuda" and torch.cuda.is_available()
            device = "cuda" if use_cuda else "cpu"
            self._extractor = FeatureExtractor(model_name="osnet_x1_0", device=device)
            self._available = True
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("_AppearanceEmbedder unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def extract(self, crop: np.ndarray | None) -> list[float]:
        if not self._available or self._extractor is None or crop is None or crop.size == 0:
            return []
        try:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            features = self._extractor([rgb]).cpu().numpy().reshape(-1)
            return _normalize(features, int(self._cfg.get("embedding_dim", 512))).astype(float).tolist()
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("_AppearanceEmbedder.extract failed: %s", exc)
            return []


@dataclass
class IdentityResolution:
    identity_id: str
    confidence_score: float
    face_embedding: list[float]
    appearance_embedding: list[float]
    source_scores: dict[str, float] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    operator_review_required: bool = True
    match_type: str = "possible_identity_match"


class IdentityFusionEngine:
    """
    Embedding-based identity resolution across cameras with configurable
    face/ReID fusion, face quality gating, and cross-camera registry history.
    """

    def __init__(
        self,
        db: IdentityDB | None = None,
        similarity_threshold: float | None = None,
        face_embedder: _FaceEmbedder | None = None,
        appearance_embedder: _AppearanceEmbedder | None = None,
    ) -> None:
        system_boot_check()
        self._cfg = load_identity_config()
        self._face_cfg = self._cfg.get("face", {})
        self._reid_cfg = self._cfg.get("reid", {})
        self._fusion_cfg = self._cfg.get("fusion", {})
        self._db = db or get_db()
        self._face = face_embedder or _FaceEmbedder(self._face_cfg)
        self._appearance = appearance_embedder or _AppearanceEmbedder(self._reid_cfg)
        self._similarity_threshold = float(
            similarity_threshold
            if similarity_threshold is not None
            else self._fusion_cfg.get("min_fused_confidence", 0.50)
        )
        self._track_identity_map: dict[str, str] = {}
        self._track_history: dict[str, deque[tuple[str, float]]] = {}
        self._candidate_emit_last: dict[str, float] = {}
        self._last_error: str | None = self._face.last_error or self._appearance.last_error

    @property
    def face_available(self) -> bool:
        return self._face.available

    @property
    def appearance_available(self) -> bool:
        return self._appearance.available

    def get_health(self) -> dict[str, Any]:
        face_enabled = bool(self._face_cfg.get("enabled", True))
        reid_enabled = bool(self._reid_cfg.get("enabled", True))
        if not bool(self._cfg.get("enabled", True)):
            status = "disabled"
        elif (face_enabled and not self._face.available) or (reid_enabled and not self._appearance.available):
            status = "degraded" if bool(self._cfg.get("fail_open", True)) else "failed"
        else:
            status = "healthy"
        return {
            "enabled": bool(self._cfg.get("enabled", True)),
            "face_provider": self._face.backend,
            "face_loaded": self._face.available,
            "reid_provider": self._appearance.backend,
            "reid_loaded": self._appearance.available,
            "liveness_enabled": bool(self._cfg.get("liveness", {}).get("enabled", False)),
            "status": status,
            "last_error": self._last_error,
        }

    def get_status(self) -> dict[str, Any]:
        return self.get_health()

    def annotate_detections(self, packet: FramePacket) -> None:
        from inference.monitoring.metrics import get_metrics

        for detection in packet.detections:
            detection.camera_id = packet.camera_id
            crop = self._extract_crop(packet.image, detection.bbox)
            face_region = self._extract_face_region(crop)
            face_info = self._face.analyze(face_region)
            if face_info:
                get_metrics().increment("identity_face_detections_total")
                quality = score_face_quality(
                    face_region,
                    detection_score=face_info.get("detection_score"),
                    pose=face_info.get("pose"),
                    embedding=face_info.get("embedding"),
                    min_face_size_px=int(self._face_cfg.get("min_face_size_px", 40)),
                    min_detection_score=float(self._face_cfg.get("min_detection_score", 0.60)),
                    min_quality_score=float(self._face_cfg.get("min_quality_score", 0.55)),
                )
                detection.metadata["face_quality"] = quality
                if quality["is_usable"]:
                    detection.face_embedding = list(face_info.get("embedding", []))
                else:
                    detection.face_embedding = []
                    get_metrics().increment("identity_face_quality_rejected_total")
            else:
                detection.metadata["face_quality"] = {
                    "quality_score": 0.0,
                    "is_usable": False,
                    "reasons": ["no_face_detected"],
                    "metrics": {},
                }
                detection.face_embedding = []

            area = 0.0
            if crop is not None and crop.size != 0:
                area = float(crop.shape[0] * crop.shape[1])
            if area >= float(self._reid_cfg.get("min_person_box_area_px", 2500)):
                detection.appearance_embedding = self._appearance.extract(crop)
            else:
                detection.appearance_embedding = []
            if detection.face_embedding or detection.appearance_embedding:
                get_metrics().increment("identity_embeddings_created_total")

    def resolve_track(
        self,
        packet: FramePacket,
        track: Track,
        detection: Detection | None = None,
    ) -> IdentityResolution:
        from inference.identity.global_identity_registry import get_global_registry
        from inference.monitoring.metrics import get_metrics

        t0 = time.monotonic()
        if detection is not None:
            face_embedding = list(detection.face_embedding or [])
            appearance_embedding = list(detection.appearance_embedding or [])
            quality = dict(detection.metadata.get("face_quality", {}))
        else:
            temp_detection = Detection(
                class_name=track.class_name,
                bbox=list(track.bbox),
                confidence=float(track.confidence),
                source_model="tracker",
                camera_id=packet.camera_id,
            )
            self.annotate_detections(FramePacket(frame_id=packet.frame_id, camera_id=packet.camera_id, image=packet.image, detections=[temp_detection]))
            face_embedding = list(temp_detection.face_embedding or [])
            appearance_embedding = list(temp_detection.appearance_embedding or [])
            quality = dict(temp_detection.metadata.get("face_quality", {}))

        candidate_ids: set[str] = set()
        face_hits = self._db.search_top_k(face_embedding, k=5, modality="face") if face_embedding else []
        reid_hits = self._db.search_top_k(appearance_embedding, k=5, modality="appearance") if appearance_embedding else []
        for hit in face_hits + reid_hits:
            candidate_ids.add(hit["identity_id"])
        if appearance_embedding:
            for hit in get_global_registry().search_global(appearance_embedding, k=5, exclude_stream=packet.camera_id):
                candidate_ids.add(hit["identity_id"])

        best_identity_id: str | None = None
        best_score = 0.0
        best_sources = {"face": 0.0, "reid": 0.0, "track": 0.0}
        face_weight = float(self._fusion_cfg.get("face_weight", 0.65))
        reid_weight = float(self._fusion_cfg.get("reid_weight", 0.35))

        for identity_id in candidate_ids:
            record = self._db.vector_store.get_identity(identity_id)
            if record is None:
                continue
            face_score = _cosine_similarity(face_embedding, record.get("face_embedding", []), int(self._face_cfg.get("embedding_dim", 512)))
            reid_score = _cosine_similarity(appearance_embedding, record.get("appearance_embedding", []), int(self._reid_cfg.get("embedding_dim", 512)))
            track_score = self._temporal_track_consistency(track, identity_id)
            fused_modal = face_weight * face_score + reid_weight * reid_score
            fused_score = 0.85 * fused_modal + 0.15 * track_score
            if not face_embedding and bool(self._fusion_cfg.get("require_face_for_high_confidence", False)):
                fused_score = min(fused_score, 0.74)
            if quality and not quality.get("is_usable", False) and face_score > float(self._face_cfg.get("match_threshold", 0.42)):
                fused_score = min(fused_score, 0.69)
            if fused_score > best_score:
                best_score = fused_score
                best_identity_id = identity_id
                best_sources = {
                    "face": round(float(face_score), 4),
                    "reid": round(float(reid_score), 4),
                    "track": round(float(track_score), 4),
                }

        operator_review_required = True
        match_type = "unknown_person"
        min_fused = float(self._fusion_cfg.get("min_fused_confidence", 0.50))
        if best_identity_id is None or best_score < min_fused:
            best_identity_id = f"{_TEMP_PREFIX}{uuid.uuid4()}"
            best_score = max(best_score, min(0.49, 0.20 + 0.50 * float(getattr(track, "stability_score", 0.0))))
            get_metrics().increment("identity_unknowns_total")
        else:
            operator_review_required = best_score < 0.80
            match_type = "possible_identity_match"
            get_metrics().increment("identity_matches_total")
            if best_sources["reid"] >= float(self._reid_cfg.get("match_threshold", 0.55)):
                get_metrics().increment("identity_reid_matches_total")

        track_key = self._track_key(track)
        history = self._track_history.setdefault(track_key, deque(maxlen=_HISTORY_LEN))
        history.append((best_identity_id, best_score))
        smoothed_id = self._weighted_majority_vote(history)
        self._track_identity_map[track_key] = smoothed_id
        final_conf = round(max(0.0, min(1.0, best_score)), 4)

        if not smoothed_id.startswith(_TEMP_PREFIX):
            self._db.persist_identity(
                identity_id=smoothed_id,
                face_embedding=face_embedding or None,
                appearance_embedding=appearance_embedding or None,
                metadata={
                    "camera_id": packet.camera_id,
                    "track_id": track.track_id,
                    "class_name": track.class_name,
                },
            )
            get_global_registry().register_identity(
                stream_id=packet.camera_id,
                embedding=appearance_embedding or face_embedding,
                identity_id=smoothed_id,
                confidence=final_conf,
                source_scores=best_sources,
                source="fusion",
            )
        elif best_sources["face"] and best_sources["reid"] and abs(best_sources["face"] - best_sources["reid"]) > 0.45:
            get_global_registry().record_conflict(smoothed_id, "temporary_conflict", {"source_scores": best_sources})

        get_metrics().record_identity_confidence(final_conf)
        get_metrics().record_segmentation_value("identity_fusion_latency_ms", round((time.monotonic() - t0) * 1000.0, 2))
        get_metrics().record_segmentation_value(
            "identity_registry_active_count",
            get_global_registry().total_identities,
        )

        try:
            review = dict(self._cfg.get("review") or {})
            emit_threshold = float(review.get("candidate_emit_min_fusion_score", 0.55))
        except (TypeError, ValueError):
            emit_threshold = 0.55
        emit_key = f"{smoothed_id}|{packet.camera_id}|{track.track_uuid}"
        now_emit = time.time()
        if (
            not smoothed_id.startswith(_TEMP_PREFIX)
            and match_type == "possible_identity_match"
            and final_conf >= emit_threshold
            and now_emit - float(self._candidate_emit_last.get(emit_key, 0.0)) > 30.0
        ):
            self._candidate_emit_last[emit_key] = now_emit
            try:
                from core.event_bus import EventType, get_event_bus

                live_cfg = dict(self._cfg.get("liveness") or {})
                payload = {
                    "global_identity_id": smoothed_id,
                    "camera_id": packet.camera_id,
                    "source_event_id": None,
                    "face_score": best_sources.get("face"),
                    "reid_score": best_sources.get("reid"),
                    "fusion_score": final_conf,
                    "track_continuity_score": best_sources.get("track"),
                    "quality_score": float(quality.get("quality_score") or 0.0) if quality else None,
                    "liveness_enabled_snapshot": bool(live_cfg.get("enabled", False)),
                    "liveness_status": str(live_cfg.get("provider") or "none"),
                    "camera_observations": [{"camera_id": packet.camera_id, "track_id": track.track_id}],
                    "first_seen": now_emit,
                    "last_seen": now_emit,
                    "evidence_refs": [{"type": "track_ref", "ref": f"{packet.camera_id}:{track.track_uuid}"}],
                    "review_status": "pending",
                }
                get_event_bus().publish(
                    EventType.IDENTITY_CANDIDATE_CREATED,
                    payload,
                    source=packet.camera_id,
                    priority=4,
                )
            except Exception:
                pass

        return IdentityResolution(
            identity_id=smoothed_id,
            confidence_score=final_conf,
            face_embedding=face_embedding,
            appearance_embedding=appearance_embedding,
            source_scores=best_sources,
            quality=quality,
            operator_review_required=operator_review_required,
            match_type=match_type,
        )

    @staticmethod
    def _weighted_majority_vote(history: deque[tuple[str, float]]) -> str:
        weights: dict[str, float] = {}
        for identity_id, confidence in history:
            weights[identity_id] = weights.get(identity_id, 0.0) + confidence
        return max(weights, key=lambda item: weights[item])

    def _temporal_track_consistency(self, track: Track, candidate_identity_id: str) -> float:
        assigned = self._track_identity_map.get(self._track_key(track))
        if assigned == candidate_identity_id:
            return 1.0
        if track.identity_id == candidate_identity_id:
            return 0.95
        freshness = max(0.0, 1.0 - min(getattr(track, "missed_frames", 0), 10) / 10.0)
        stability = float(getattr(track, "stability_score", 0.0) or 0.0)
        return round(min(1.0, 0.50 * stability + 0.50 * freshness), 4)

    @staticmethod
    def _track_key(track: Track) -> str:
        return f"{track.camera_id}:{track.track_uuid}"

    @staticmethod
    def _extract_crop(frame: np.ndarray | None, bbox: list[float]) -> np.ndarray | None:
        if frame is None or frame.size == 0:
            return None
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2].copy()

    @staticmethod
    def _extract_face_region(crop: np.ndarray | None) -> np.ndarray | None:
        if crop is None or crop.size == 0:
            return None
        height, width = crop.shape[:2]
        top = int(height * 0.45)
        pad = int(width * 0.20)
        x1 = pad
        x2 = max(x1 + 1, width - pad)
        return crop[:top, x1:x2].copy()
