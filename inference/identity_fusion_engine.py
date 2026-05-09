from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np

from inference.identity_db import IdentityDB, get_db
from inference.schemas import Detection, FramePacket, Track
from ml.runtime import ModelRouter, system_boot_check

logger = logging.getLogger(__name__)

_FACE_WEIGHT = 0.50
_APPEARANCE_WEIGHT = 0.30
_TEMPORAL_WEIGHT = 0.20

# Phase 5 — confidence & smoothing constants
MIN_IDENTITY_CONFIDENCE: float = 0.60   # below this → assign TEMP_ identity
_HISTORY_LEN: int = 5                    # frames of identity matches to smooth over
_TEMP_PREFIX: str = "TEMP_"


def _cosine_similarity(left: list[float] | np.ndarray, right: list[float] | np.ndarray, dim: int = 512) -> float:
    lhs = _normalize(left, dim)
    rhs = _normalize(right, dim)
    denom = float(np.linalg.norm(lhs) * np.linalg.norm(rhs))
    if denom == 0.0:
        return 0.0
    return float(np.dot(lhs, rhs))


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


def _normalize_embedding_list(values: list[float] | np.ndarray | None, label: str) -> list[float]:
    try:
        return _normalize(values).astype(float).tolist()
    except RuntimeError as exc:
        raise RuntimeError(f"{label} embedding unavailable - system cannot operate safely") from exc


class _FaceEmbedder:
    """
    InsightFace-backed face embedder with graceful degradation.

    If InsightFace is unavailable (missing bundle, import error, etc.),
    the embedder initialises in degraded mode and returns empty lists
    instead of raising.  The system continues with IoU-only tracking.
    """

    def __init__(self) -> None:
        self._app = None
        self._available = False
        self.backend = "insightface"
        try:
            system_boot_check()
            from insightface.app import FaceAnalysis

            model_meta = ModelRouter().get_model("face")
            model_path = Path(model_meta["resolved_path"])
            if model_path.parent.name != "models":
                raise RuntimeError(
                    "Face model path must resolve to <project>/models/<bundle_name> for InsightFace boot."
                )
            import torch
            _cuda = torch.cuda.is_available()
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if _cuda
                else ["CPUExecutionProvider"]
            )
            ctx_id = 0 if _cuda else -1   # 0 = first GPU, -1 = CPU
            self._app = FaceAnalysis(
                name=model_path.name,
                root=str(model_path.parent.parent),
                providers=providers,
            )
            self._app.prepare(ctx_id=ctx_id)
            self._available = True
            logger.info("_FaceEmbedder: InsightFace loaded successfully.")
        except Exception as exc:
            logger.warning(
                "_FaceEmbedder: InsightFace unavailable — running without face embeddings. "
                "Reason: %s", exc,
            )

    @property
    def available(self) -> bool:
        return self._available

    def extract(self, face_crop: np.ndarray | None) -> list[float]:
        if not self._available or self._app is None:
            return []
        if face_crop is None or face_crop.size == 0:
            return []
        try:
            faces = self._app.get(face_crop)
            if not faces:
                return []
            return _normalize_embedding_list(faces[0].normed_embedding, "face")
        except Exception as exc:
            logger.debug("_FaceEmbedder.extract failed: %s", exc)
            return []


class _AppearanceEmbedder:
    """
    OSNet-backed appearance embedder with graceful degradation and CUDA fallback.

    Runs on GPU when available; falls back to CPU automatically.
    If OSNet is unavailable entirely, returns empty lists.
    """

    def __init__(self) -> None:
        self._extractor = None
        self._available = False
        self.backend = "osnet"
        try:
            system_boot_check()
            import torch
            from torchreid.reid.utils import FeatureExtractor

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._extractor = FeatureExtractor(model_name="osnet_x1_0", device=device)
            self._available = True
            logger.info("_AppearanceEmbedder: OSNet loaded on %s.", device)
        except Exception as exc:
            logger.warning(
                "_AppearanceEmbedder: OSNet unavailable — running without appearance embeddings. "
                "Reason: %s", exc,
            )

    @property
    def available(self) -> bool:
        return self._available

    def extract(self, crop: np.ndarray | None) -> list[float]:
        if not self._available or self._extractor is None:
            return []
        if crop is None or crop.size == 0:
            return []
        try:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            features = self._extractor([rgb]).cpu().numpy().reshape(-1)
            return _normalize_embedding_list(features, "appearance")
        except Exception as exc:
            logger.debug("_AppearanceEmbedder.extract failed: %s", exc)
            return []


@dataclass
class IdentityResolution:
    identity_id: str
    confidence_score: float
    face_embedding: list[float]
    appearance_embedding: list[float]


class IdentityFusionEngine:
    """
    Embedding-based identity resolution across cameras.

    Operates in full mode (InsightFace + OSNet) or degraded mode
    (UUID-only assignment) depending on embedder availability.
    """

    def __init__(
        self,
        db: IdentityDB | None = None,
        similarity_threshold: float = 0.58,
        face_embedder: _FaceEmbedder | None = None,
        appearance_embedder: _AppearanceEmbedder | None = None,
    ) -> None:
        system_boot_check()
        self._db = db or get_db()
        self._face = face_embedder or _FaceEmbedder()
        self._appearance = appearance_embedder or _AppearanceEmbedder()
        self._similarity_threshold = similarity_threshold
        # Phase 5: per-track history deque[(identity_id, confidence)] for smoothing
        self._track_identity_map: dict[str, str] = {}
        self._track_history: dict[str, deque[tuple[str, float]]] = {}
        if not self._face.available and not self._appearance.available:
            logger.critical(
                "IdentityFusionEngine: CRITICAL DEGRADED MODE — both face and appearance "
                "embedders are unavailable. Identity tracking is UUID-only with no "
                "cross-frame or cross-camera matching.",
            )
        elif not self._face.available or not self._appearance.available:
            logger.warning(
                "IdentityFusionEngine: running in DEGRADED MODE — "
                "face_available=%s, appearance_available=%s. "
                "Identity tracking will assign new UUIDs without cross-frame matching.",
                self._face.available, self._appearance.available,
            )

    @property
    def face_available(self) -> bool:
        return self._face.available

    @property
    def appearance_available(self) -> bool:
        return self._appearance.available

    @property
    def model_status(self) -> dict[str, str]:
        return {
            "face_embedding": f"{self._face.backend}:{'ok' if self._face.available else 'degraded'}",
            "appearance_embedding": f"{self._appearance.backend}:{'ok' if self._appearance.available else 'degraded'}",
        }

    def get_status(self) -> Dict[str, bool]:
        return {
            "face": self._face.available,
            "appearance": self._appearance.available,
        }

    def annotate_detections(self, packet: FramePacket) -> None:
        for detection in packet.detections:
            detection.camera_id = packet.camera_id
            if detection.face_embedding and detection.appearance_embedding:
                # Already annotated — normalize in place, ignore failures
                try:
                    detection.face_embedding = _normalize_embedding_list(detection.face_embedding, "face")
                    detection.appearance_embedding = _normalize_embedding_list(
                        detection.appearance_embedding, "appearance"
                    )
                except RuntimeError:
                    detection.face_embedding = []
                    detection.appearance_embedding = []
                continue

            crop = self._extract_crop(packet.image, detection.bbox)
            face_region = self._extract_face_region(crop)
            detection.face_embedding = self._face.extract(face_region) if face_region is not None else []
            detection.appearance_embedding = self._appearance.extract(crop) if crop is not None else []

    def resolve_track(
        self,
        packet: FramePacket,
        track: Track,
        detection: Detection | None = None,
    ) -> IdentityResolution:
        """
        Resolve the identity for *track* using embedding similarity.

        Phase-5 enhancements
        ────────────────────
        1. Confidence gating  — raw scores below MIN_IDENTITY_CONFIDENCE produce
           a TEMP_ identity instead of a persistent one.
        2. Temporal smoothing — last _HISTORY_LEN resolutions per track are
           stored; a weighted majority vote stabilises jittery assignments.
        3. Global registry    — after local FAISS search, also queries the
           cross-stream GlobalIdentityRegistry to recognise persons seen by
           other cameras.
        """
        from inference.monitoring.metrics import get_metrics

        # ── gather embeddings ─────────────────────────────────────────────────
        if detection is not None:
            face_embedding = list(detection.face_embedding or [])
            appearance_embedding = list(detection.appearance_embedding or [])
        else:
            crop = self._extract_crop(packet.image, track.bbox)
            face_region = self._extract_face_region(crop)
            face_embedding = self._face.extract(face_region) if face_region is not None else []
            appearance_embedding = self._appearance.extract(crop) if crop is not None else []

        # ── degraded mode (no embeddings) ────────────────────────────────────
        if not face_embedding or not appearance_embedding:
            stability_score = getattr(track, "stability_score", 0.0)
            confidence = round(min(0.95, 0.30 + 0.50 * stability_score), 4)
            identity_id = (
                _TEMP_PREFIX + str(uuid.uuid4())
                if confidence < MIN_IDENTITY_CONFIDENCE
                else str(uuid.uuid4())
            )
            get_metrics().record_identity_confidence(confidence)
            return IdentityResolution(
                identity_id=identity_id,
                confidence_score=confidence,
                face_embedding=[],
                appearance_embedding=[],
            )

        # ── local FAISS search ────────────────────────────────────────────────
        face_hits = self._db.search_top_k(face_embedding, k=5, modality="face")
        appearance_hits = self._db.search_top_k(appearance_embedding, k=5, modality="appearance")
        candidate_ids: set[str] = {hit["identity_id"] for hit in face_hits + appearance_hits}

        # ── global registry search (cross-stream) ────────────────────────────
        try:
            from inference.identity.global_identity_registry import get_global_registry
            global_hits = get_global_registry().search_global(
                appearance_embedding, k=5, exclude_stream=packet.camera_id,
            )
            for hit in global_hits:
                candidate_ids.add(hit["identity_id"])
            if global_hits:
                get_metrics().record_cross_stream_match(len(global_hits))
        except Exception:
            pass  # global registry failure must never block local resolution

        # ── cosine re-rank over all candidates ────────────────────────────────
        best_identity_id: str | None = None
        best_score: float = 0.0
        for identity_id in candidate_ids:
            record = self._db.vector_store.get_identity(identity_id)
            if record is None:
                continue
            face_score = _cosine_similarity(face_embedding, record["face_embedding"])
            appearance_score = _cosine_similarity(appearance_embedding, record["appearance_embedding"])
            temporal_score = self._temporal_track_consistency(track, identity_id)
            identity_score = (
                _FACE_WEIGHT * face_score
                + _APPEARANCE_WEIGHT * appearance_score
                + _TEMPORAL_WEIGHT * temporal_score
            )
            if identity_score > best_score:
                best_score = identity_score
                best_identity_id = identity_id

        # ── confidence gating ─────────────────────────────────────────────────
        if best_identity_id is None or best_score < self._similarity_threshold:
            raw_conf = max(best_score, min(0.95, 0.30 + 0.50 * track.stability_score))
            best_score = raw_conf
            best_identity_id = (
                _TEMP_PREFIX + str(uuid.uuid4())
                if raw_conf < MIN_IDENTITY_CONFIDENCE
                else str(uuid.uuid4())
            )

        # ── temporal smoothing (weighted majority vote) ───────────────────────
        track_key = self._track_key(track)
        history = self._track_history.setdefault(track_key, deque(maxlen=_HISTORY_LEN))
        history.append((best_identity_id, best_score))
        smoothed_id = self._weighted_majority_vote(history)
        # Update the fast lookup map used by _temporal_track_consistency
        self._track_identity_map[track_key] = smoothed_id

        # ── persist to local DB + global registry ────────────────────────────
        final_conf = round(min(1.0, max(0.0, best_score)), 4)
        if not smoothed_id.startswith(_TEMP_PREFIX):
            self._db.persist_identity(
                identity_id=smoothed_id,
                face_embedding=face_embedding,
                appearance_embedding=appearance_embedding,
                metadata={
                    "camera_id": packet.camera_id,
                    "track_id": track.track_id,
                    "class_name": track.class_name,
                },
            )
            try:
                from inference.identity.global_identity_registry import get_global_registry
                get_global_registry().register_identity(
                    stream_id=packet.camera_id,
                    embedding=appearance_embedding,
                    identity_id=smoothed_id,
                )
            except Exception:
                pass

        get_metrics().record_identity_confidence(final_conf)
        return IdentityResolution(
            identity_id=smoothed_id,
            confidence_score=final_conf,
            face_embedding=face_embedding,
            appearance_embedding=appearance_embedding,
        )

    @staticmethod
    def _weighted_majority_vote(history: deque[tuple[str, float]]) -> str:
        """
        Pick the identity_id with the highest total confidence weight across
        the recent _HISTORY_LEN observations.  This smooths jitter caused by
        single low-confidence mismatches between consecutive frames.
        """
        weights: dict[str, float] = {}
        for identity_id, conf in history:
            weights[identity_id] = weights.get(identity_id, 0.0) + conf
        return max(weights, key=lambda k: weights[k])

    def _temporal_track_consistency(self, track: Track, candidate_identity_id: str) -> float:
        assigned = self._track_identity_map.get(self._track_key(track))
        if assigned == candidate_identity_id:
            return 1.0
        if track.identity_id == candidate_identity_id:
            return 0.95
        freshness = max(0.0, 1.0 - min(track.missed_frames, 10) / 10.0)
        return round(min(1.0, 0.50 * track.stability_score + 0.50 * freshness), 4)

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
