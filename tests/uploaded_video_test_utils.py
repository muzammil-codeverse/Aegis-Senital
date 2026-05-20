from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from starlette.datastructures import UploadFile

from app.repositories.case_repository import JsonlCaseRepository
from app.repositories.incident_repository import JsonlIncidentRepository
from app.services.case_service import CaseService


def create_test_video(path: Path, *, frame_count: int = 6, fps: float = 6.0, size: tuple[int, int] = (48, 48)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        size,
    )
    if not writer.isOpened():
        raise RuntimeError(f"Unable to create test video at {path}")
    for index in range(frame_count):
        frame = np.full((size[1], size[0], 3), (index * 20) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def build_upload_file(path: Path) -> UploadFile:
    return UploadFile(
        filename=path.name,
        file=BytesIO(path.read_bytes()),
        headers={"content-type": "video/x-msvideo"},
    )


def uploaded_video_config(tmp_path: Path) -> dict:
    return {
        "uploaded_video": {
            "enabled": True,
            "storage": {
                "root_dir": str(tmp_path / "uploaded_videos"),
                "processed_dir": str(tmp_path / "uploaded_video_results"),
                "evidence_dir": str(tmp_path / "evidence"),
                "command_center_dir": str(tmp_path / "command_center_intelligence"),
                "require_managed_storage_in_production": False,
            },
            "upload": {
                "max_file_size_mb": 750,
                "allowed_extensions": [".mp4", ".avi", ".mov", ".mkv"],
                "require_upload_policy": True,
                "compute_sha256": True,
            },
            "processing": {
                "default_device": "cpu",
                "target_fps": 6,
                "max_frames": 4,
                "frame_stride": 1,
                "queue_size": 8,
                "drop_policy": "drop_oldest",
                "reuse_stream_processor": True,
                "generate_event_timeline": True,
                "generate_snapshots": True,
                "generate_replay_clips": False,
            },
            "case_integration": {
                "allow_create_case_from_video": True,
                "auto_case_min_severity": "high",
                "attach_source_video_as_evidence": True,
                "attach_snapshots_as_evidence": True,
            },
            "reporting": {
                "generate_summary_report": True,
                "include_chain_of_custody": True,
                "include_model_caveats": True,
            },
            "replay": {
                "enabled": False,
                "clip_seconds_before": 1,
                "clip_seconds_after": 1,
                "output_dir": str(tmp_path / "uploaded_video_results"),
                "attach_clips_as_evidence": True,
                "compute_sha256": True,
            },
        }
    }


def build_case_service(tmp_path: Path):
    config = {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "evidence": {"max_items_per_case": 50},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }
    return CaseService(repository=JsonlCaseRepository(config=config), config=config)


def build_incident_repository(tmp_path: Path):
    return JsonlIncidentRepository(str(tmp_path / "incidents"))


class FakeModelPool:
    def __init__(self):
        self.is_loaded = True

    def load_all(self):
        self.is_loaded = True


class _FakeEvent:
    def __init__(self, frame_index: int) -> None:
        self.frame_index = frame_index

    def to_dict(self) -> dict:
        return {
            "event_id": f"uvevt_{self.frame_index}",
            "event_type": "weapon_detected",
            "severity": "high",
            "risk_score": 0.91,
            "confidence_score": 0.84,
            "track_ids": [f"trk_{self.frame_index}"],
            "summary": "Possible weapon-related event detected. Operator review required.",
        }


class FakeStreamProcessor:
    def __init__(self, stream_id: str, source: str, model_pool: FakeModelPool) -> None:
        del source, model_pool
        self.stream_id = stream_id
        self.camera_id = stream_id

    def process_decoded_packet(self, decoded_packet) -> dict:
        event = _FakeEvent(decoded_packet.frame_index)
        return {
            "events": [event],
            "anomalies": [],
            "incidents": [],
            "scenarios": [],
            "intelligence": {"incidents": [], "alerts": []},
            "packet": None,
        }
