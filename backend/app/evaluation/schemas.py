"""
Phase 25 — Evaluation schemas.

Strict dataclass-based schemas for all benchmark artifacts.
No fake data. No fabricated metrics.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_hash(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class DetectionMetricResult:
    map_50: float | None = None
    map_50_95: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    per_class_ap: dict[str, float] = field(default_factory=dict)
    false_positives_per_image: float | None = None
    false_negatives_per_image: float | None = None
    iou_distribution: dict[str, float] = field(default_factory=dict)
    confusion_matrix: list[list[int]] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    confidence_calibration_buckets: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "map_50": self.map_50,
            "map_50_95": self.map_50_95,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "per_class_ap": self.per_class_ap,
            "false_positives_per_image": self.false_positives_per_image,
            "false_negatives_per_image": self.false_negatives_per_image,
            "iou_distribution": self.iou_distribution,
            "confusion_matrix": self.confusion_matrix,
            "class_names": self.class_names,
            "confidence_calibration_buckets": self.confidence_calibration_buckets,
            "warnings": self.warnings,
        }


@dataclass
class TrackingMetricResult:
    mota: float | None = None
    motp: float | None = None
    idf1: float | None = None
    hota: float | None = None
    id_switches: int | None = None
    fragmentation: int | None = None
    mostly_tracked: float | None = None
    mostly_lost: float | None = None
    avg_track_duration_frames: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mota": self.mota,
            "motp": self.motp,
            "idf1": self.idf1,
            "hota": self.hota,
            "id_switches": self.id_switches,
            "fragmentation": self.fragmentation,
            "mostly_tracked": self.mostly_tracked,
            "mostly_lost": self.mostly_lost,
            "avg_track_duration_frames": self.avg_track_duration_frames,
            "warnings": self.warnings,
        }


@dataclass
class FaceMetricResult:
    far: float | None = None
    frr: float | None = None
    tar_at_far_thresholds: dict[str, float] = field(default_factory=dict)
    roc_curve_points: list[dict] = field(default_factory=list)
    threshold_sweep: list[dict] = field(default_factory=list)
    embedding_quality_distribution: dict[str, float] = field(default_factory=dict)
    face_detection_success_rate: float | None = None
    low_quality_rejection_count: int | None = None
    recommended_threshold: float | None = None
    threshold_recommendation_note: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "far": self.far,
            "frr": self.frr,
            "tar_at_far_thresholds": self.tar_at_far_thresholds,
            "roc_curve_points": self.roc_curve_points,
            "threshold_sweep": self.threshold_sweep,
            "embedding_quality_distribution": self.embedding_quality_distribution,
            "face_detection_success_rate": self.face_detection_success_rate,
            "low_quality_rejection_count": self.low_quality_rejection_count,
            "recommended_threshold": self.recommended_threshold,
            "threshold_recommendation_note": self.threshold_recommendation_note,
            "warnings": self.warnings,
        }


@dataclass
class ReIDMetricResult:
    rank_1: float | None = None
    rank_5: float | None = None
    map: float | None = None
    cmc_curve: list[dict] = field(default_factory=list)
    intra_identity_distance_avg: float | None = None
    inter_identity_distance_avg: float | None = None
    embedding_failure_count: int = 0
    similarity_distribution: dict[str, float] = field(default_factory=dict)
    overlap_or_leakage_detected: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rank_1": self.rank_1,
            "rank_5": self.rank_5,
            "map": self.map,
            "cmc_curve": self.cmc_curve,
            "intra_identity_distance_avg": self.intra_identity_distance_avg,
            "inter_identity_distance_avg": self.inter_identity_distance_avg,
            "embedding_failure_count": self.embedding_failure_count,
            "similarity_distribution": self.similarity_distribution,
            "overlap_or_leakage_detected": self.overlap_or_leakage_detected,
            "warnings": self.warnings,
        }


@dataclass
class IdentityMetricResult:
    merge_precision: float | None = None
    merge_recall: float | None = None
    false_merge_rate: float | None = None
    false_split_rate: float | None = None
    identity_persistence_duration_avg: float | None = None
    cross_camera_association_accuracy: float | None = None
    expired_identity_count: int = 0
    re_associated_identity_count: int = 0
    scenario_results: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "merge_precision": self.merge_precision,
            "merge_recall": self.merge_recall,
            "false_merge_rate": self.false_merge_rate,
            "false_split_rate": self.false_split_rate,
            "identity_persistence_duration_avg": self.identity_persistence_duration_avg,
            "cross_camera_association_accuracy": self.cross_camera_association_accuracy,
            "expired_identity_count": self.expired_identity_count,
            "re_associated_identity_count": self.re_associated_identity_count,
            "scenario_results": self.scenario_results,
            "warnings": self.warnings,
        }


@dataclass
class OpenVocabPromptMetricResult:
    prompt_id: str = ""
    prompt_text: str = ""
    threshold: float = 0.35
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    avg_iou: float | None = None
    avg_latency_ms: float | None = None
    detections_count: int = 0
    score_distribution: dict[str, float] = field(default_factory=dict)
    false_positive_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "prompt_text": self.prompt_text,
            "threshold": self.threshold,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "avg_iou": self.avg_iou,
            "avg_latency_ms": self.avg_latency_ms,
            "detections_count": self.detections_count,
            "score_distribution": self.score_distribution,
            "false_positive_categories": self.false_positive_categories,
        }


@dataclass
class OpenVocabMetricResult:
    prompt_results: list[OpenVocabPromptMetricResult] = field(default_factory=list)
    avg_latency_per_image_ms: float | None = None
    total_images: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "prompt_results": [p.to_dict() for p in self.prompt_results],
            "avg_latency_per_image_ms": self.avg_latency_per_image_ms,
            "total_images": self.total_images,
            "warnings": self.warnings,
        }


@dataclass
class LatencyStageResult:
    stage: str = ""
    p50_ms: float | None = None
    p90_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None
    max_ms: float | None = None
    avg_ms: float | None = None
    samples: int = 0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "p50_ms": self.p50_ms,
            "p90_ms": self.p90_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "max_ms": self.max_ms,
            "avg_ms": self.avg_ms,
            "samples": self.samples,
        }


@dataclass
class LatencyMetricResult:
    stages: list[LatencyStageResult] = field(default_factory=list)
    avg_fps: float | None = None
    dropped_frames: int = 0
    queue_wait_time_avg_ms: float | None = None
    total_frames_profiled: int = 0
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "avg_fps": self.avg_fps,
            "dropped_frames": self.dropped_frames,
            "queue_wait_time_avg_ms": self.queue_wait_time_avg_ms,
            "total_frames_profiled": self.total_frames_profiled,
            "duration_seconds": self.duration_seconds,
            "warnings": self.warnings,
        }


@dataclass
class GPUProfileResult:
    gpu_available: bool = False
    gpu_name: str | None = None
    cuda_version: str | None = None
    torch_cuda_version: str | None = None
    memory_allocated_mb: float | None = None
    memory_reserved_mb: float | None = None
    peak_memory_mb: float | None = None
    utilization_percent: float | None = None
    inference_latency_ms: float | None = None
    batch_size: int | None = None
    model_loaded: bool = False
    profiling_degraded: bool = False
    degradation_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "cuda_version": self.cuda_version,
            "torch_cuda_version": self.torch_cuda_version,
            "memory_allocated_mb": self.memory_allocated_mb,
            "memory_reserved_mb": self.memory_reserved_mb,
            "peak_memory_mb": self.peak_memory_mb,
            "utilization_percent": self.utilization_percent,
            "inference_latency_ms": self.inference_latency_ms,
            "batch_size": self.batch_size,
            "model_loaded": self.model_loaded,
            "profiling_degraded": self.profiling_degraded,
            "degradation_reason": self.degradation_reason,
        }


@dataclass
class FailureCase:
    task: str = ""
    sample_id: str = ""
    frame_id: int = 0
    camera_id: str | None = None
    failure_type: str = ""
    expected: dict = field(default_factory=dict)
    actual: dict = field(default_factory=dict)
    confidence: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "sample_id": self.sample_id,
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "failure_type": self.failure_type,
            "expected": self.expected,
            "actual": self.actual,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass
class BenchmarkTaskResult:
    task: str = ""
    model_name: str = ""
    model_path: str = ""
    model_version: str | None = None
    device: str = "cpu"
    dataset_name: str = ""
    dataset_version: str | None = None
    metrics: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    failure_cases_count: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "model_name": self.model_name,
            "model_path": self.model_path,
            "model_version": self.model_version,
            "device": self.device,
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "failure_cases_count": self.failure_cases_count,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass
class BenchmarkRun:
    run_id: str = ""
    timestamp: str = field(default_factory=_now_iso)
    git_commit: str | None = None
    config_hash: str = ""
    config_snapshot: dict = field(default_factory=dict)
    device: str = "cpu"
    task_results: list[BenchmarkTaskResult] = field(default_factory=list)
    total_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "git_commit": self.git_commit,
            "config_hash": self.config_hash,
            "device": self.device,
            "task_results": [r.to_dict() for r in self.task_results],
            "total_warnings": self.total_warnings,
        }


@dataclass
class MetricDelta:
    metric: str = ""
    baseline: Any = None
    candidate: Any = None
    absolute_change: float | None = None
    percent_change: float | None = None
    status: str = "unchanged"  # improved | regressed | unchanged

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "absolute_change": self.absolute_change,
            "percent_change": self.percent_change,
            "status": self.status,
        }


@dataclass
class BenchmarkComparison:
    baseline_run_id: str = ""
    candidate_run_id: str = ""
    timestamp: str = field(default_factory=_now_iso)
    deltas: list[MetricDelta] = field(default_factory=list)
    overall_status: str = "pass"  # pass | warn | fail
    regression_policy: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "baseline_run_id": self.baseline_run_id,
            "candidate_run_id": self.candidate_run_id,
            "timestamp": self.timestamp,
            "deltas": [d.to_dict() for d in self.deltas],
            "overall_status": self.overall_status,
            "regression_policy": self.regression_policy,
            "warnings": self.warnings,
        }
