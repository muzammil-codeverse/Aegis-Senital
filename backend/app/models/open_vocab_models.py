from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpenVocabPrompt:
    prompt_id: str
    text: str
    category: str
    severity: str
    enabled: bool
    threshold: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "text": self.text,
            "category": self.category,
            "severity": self.severity,
            "enabled": self.enabled,
            "threshold": self.threshold,
            "metadata": self.metadata,
        }


@dataclass
class OpenVocabDetection:
    label: str
    prompt: str
    confidence: float
    bbox: list  # [x1, y1, x2, y2] normalized or pixel
    severity: str | None
    source_model: str
    frame_id: int | None
    camera_id: str | None
    timestamp: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "prompt": self.prompt,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "severity": self.severity,
            "source_model": self.source_model,
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class OpenVocabScanRequest:
    prompts: list[str]
    camera_id: str | None = None
    frame_id: int | None = None
    incident_id: str | None = None
    source: str = "manual"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompts": self.prompts,
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "incident_id": self.incident_id,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class OpenVocabScanResult:
    scan_id: str
    camera_id: str | None
    frame_id: int | None
    incident_id: str | None
    source: str
    prompts: list[str]
    detections: list[OpenVocabDetection]
    risk_score: float
    created_at: float
    model_id: str | None
    status: str
    error: str | None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scan_id": self.scan_id,
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "incident_id": self.incident_id,
            "source": self.source,
            "prompts": self.prompts,
            "detections": [d.to_dict() for d in self.detections],
            "risk_score": self.risk_score,
            "created_at": self.created_at,
            "model_id": self.model_id,
            "status": self.status,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def unavailable(cls, reason: str, **kwargs) -> "OpenVocabScanResult":
        return cls(
            scan_id=str(uuid.uuid4()),
            camera_id=kwargs.get("camera_id"),
            frame_id=kwargs.get("frame_id"),
            incident_id=kwargs.get("incident_id"),
            source=kwargs.get("source", "manual"),
            prompts=kwargs.get("prompts", []),
            detections=[],
            risk_score=0.0,
            created_at=time.time(),
            model_id=None,
            status="unavailable",
            error=reason,
            metadata={},
        )


@dataclass
class OpenVocabThreatRule:
    rule_id: str
    prompt_ids: list[str]
    action: str
    min_confidence: float
    enabled: bool
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "prompt_ids": self.prompt_ids,
            "action": self.action,
            "min_confidence": self.min_confidence,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class OpenVocabScanJob:
    job_id: str
    request: OpenVocabScanRequest
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "request": self.request.to_dict(),
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result_id": self.result_id,
            "error": self.error,
        }
