from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.event_bus import EventType, get_event_bus
from app.models.case_models import (
    CASE_EVIDENCE_TYPES,
    CASE_PRIORITIES,
    CASE_SEVERITIES,
    CASE_STATUSES,
    CaseAssignment,
    CaseAuditLog,
    CaseCreateRequest,
    CaseEvidence,
    CaseEvidenceCreateRequest,
    CaseExport,
    CaseNote,
    CaseNoteCreateRequest,
    CaseRecord,
    CaseUpdateRequest,
)
from app.repositories.case_repository import (
    CaseRepository,
    get_case_repository,
    load_case_management_config,
)
from app.services.case_export_service import CaseExportService
from app.services.case_timeline_service import CaseTimelineService
from app.services.evidence_integrity import (
    describe_local_artifact,
    guess_content_type,
    resolve_local_storage_uri,
    safe_evidence_metadata,
)

logger = logging.getLogger(__name__)

_CASE_SERVICE: "CaseService | None" = None
_CASE_SERVICE_SUBSCRIBED = False

_SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_FORBIDDEN_PHRASES = {
    "criminal confirmed": "possible incident requires operator review",
    "suspect guilty": "unknown person requires operator review",
    "attack confirmed": "possible incident requires operator review",
    "threat confirmed": "possible threat-related event requires operator review",
    "identity confirmed": "possible identity match requires operator review",
}
_AUTO_TITLES = {
    "weapon_detected": "Possible weapon-related event",
    "open_vocab_scan_result": "Possible open-vocabulary incident",
    "anomaly_event": "Possible anomaly incident",
    "identity_match": "Possible identity-match incident",
    "restricted_zone_intrusion": "Possible restricted-zone incident",
}
_EVIDENCE_TYPE_BY_EVENT = {
    "weapon_detected": "event",
    "open_vocab_scan_result": "detection",
    "anomaly_event": "anomaly",
    "identity_match": "identity",
    "restricted_zone_intrusion": "event",
    # Phase 45 — drone patrol mission evidence types (all simulated)
    "drone_mission_report": "drone_mission_report",
    "drone_mission_telemetry_manifest": "drone_mission_telemetry_manifest",
    "drone_mission_event": "drone_mission_event",
}
_ALLOWED_STATUS_TRANSITIONS = {
    "open": {"investigating", "resolved", "dismissed", "archived"},
    "investigating": {"open", "resolved", "dismissed", "archived"},
    "resolved": {"open", "archived"},
    "dismissed": {"open", "archived"},
    "archived": {"open"},
}


class CaseService:
    def __init__(
        self,
        repository: CaseRepository | None = None,
        config: dict[str, Any] | None = None,
        timeline_service: CaseTimelineService | None = None,
        export_service: CaseExportService | None = None,
    ) -> None:
        self._raw_config = config or load_case_management_config()
        self._config = dict(self._raw_config.get("case_management") or {})
        self._repository = repository or get_case_repository()
        self._timeline_service = timeline_service or CaseTimelineService(self._repository)
        self._export_service = export_service or CaseExportService(self._repository, self._timeline_service)
        self._subscribe_event_bus()

    @property
    def repository(self) -> CaseRepository:
        return self._repository

    def create_case(self, payload: CaseCreateRequest | dict[str, Any], actor: str = "system") -> CaseRecord:
        request = payload if isinstance(payload, CaseCreateRequest) else CaseCreateRequest.model_validate(payload)
        self._ensure_available()
        now = _now_iso()
        case = CaseRecord(
            title=self._safe_text(request.title) or "Possible incident",
            description=self._safe_text(request.description),
            priority=request.priority,
            severity=request.severity,
            source_event_ids=request.source_event_ids,
            camera_ids=request.camera_ids,
            track_ids=request.track_ids,
            assigned_to=request.assigned_to,
            created_by=actor,
            created_at=now,
            updated_at=now,
            tags=self._merge_tags(request.tags, request.metadata),
            requires_review=request.requires_review,
            review_status=request.review_status,
            metadata=safe_evidence_metadata(request.metadata),
        )
        created = self._repository.create_case(case)
        self._record_case_audit(
            created.case_id,
            action="case_created",
            actor=actor,
            detail="Case created.",
            metadata={"status": created.status, "priority": created.priority},
        )
        _increment_metric("cases_created_total")
        return created

    def get_case(self, case_id: str) -> CaseRecord | None:
        return self._repository.get_case(case_id)

    def list_cases(self, filters: dict[str, Any] | None = None) -> list[CaseRecord]:
        return self._repository.list_cases(filters or {})

    def update_case(self, case_id: str, payload: CaseUpdateRequest | dict[str, Any], actor: str = "system") -> CaseRecord:
        request = payload if isinstance(payload, CaseUpdateRequest) else CaseUpdateRequest.model_validate(payload)
        current = self._require_case(case_id)
        updates = request.model_dump(exclude_none=True, mode="json")
        if "title" in updates:
            updates["title"] = self._safe_text(updates["title"])
        if "description" in updates:
            updates["description"] = self._safe_text(updates["description"])
        if "metadata" in updates:
            updates["metadata"] = safe_evidence_metadata(updates["metadata"])
        if "status" in updates:
            self._validate_status_transition(current.status, updates["status"])
            if updates["status"] in {"resolved", "dismissed", "archived"}:
                updates["closed_at"] = updates.get("closed_at") or _now_iso()
            elif updates["status"] in {"open", "investigating"}:
                updates["closed_at"] = None
        updates["updated_at"] = _now_iso()
        updated = self._repository.update_case(case_id, updates)
        action = "review_status_changed" if "review_status" in updates else "case_updated"
        detail = "Case updated."
        if "status" in updates:
            action = "status_changed"
            detail = f"Case status changed to {updates['status']}."
        self._record_case_audit(case_id, action=action, actor=actor, detail=detail, metadata={"updated_fields": sorted(updates.keys()), **updates})
        _increment_metric("cases_updated_total")
        return updated

    def delete_or_archive_case(self, case_id: str, actor: str = "system") -> CaseRecord:
        archived = self._repository.delete_or_archive_case(case_id)
        self._record_case_audit(case_id, action="case_archived", actor=actor, detail="Case archived.", metadata={})
        _increment_metric("cases_archived_total")
        return archived

    def add_evidence(self, case_id: str, payload: CaseEvidenceCreateRequest | dict[str, Any], actor: str = "system") -> CaseEvidence:
        self._require_case(case_id)
        request = payload if isinstance(payload, CaseEvidenceCreateRequest) else CaseEvidenceCreateRequest.model_validate(payload)
        max_items = int(((self._config.get("evidence") or {}).get("max_items_per_case")) or 500)
        if len(self._repository.list_evidence(case_id)) >= max_items:
            raise ValueError(f"Case '{case_id}' reached the evidence limit ({max_items})")
        integrity = self._build_integrity_payload(request.storage_uri)
        file_backed = integrity["integrity_status"] != "not_applicable"
        evidence = CaseEvidence(
            case_id=case_id,
            evidence_type=request.evidence_type,
            title=self._safe_text(request.title),
            description=self._safe_text(request.description),
            source_event_id=request.source_event_id,
            camera_id=request.camera_id,
            track_ids=request.track_ids,
            storage_uri=request.storage_uri,
            snapshot_uri=request.snapshot_uri,
            original_filename=request.original_filename or integrity["original_filename"],
            safe_filename=request.safe_filename or integrity["safe_filename"],
            content_type=request.content_type or integrity["content_type"],
            size_bytes=request.size_bytes if request.size_bytes is not None else integrity["size_bytes"],
            created_by=actor,
            timestamp=request.timestamp or _now_iso(),
            hash_sha256=integrity["hash_sha256"] if file_backed else request.hash_sha256,
            hash_verified=integrity["hash_verified"] if file_backed else request.hash_verified,
            integrity_status=integrity["integrity_status"] if file_backed else (request.integrity_status or integrity["integrity_status"]),
            chain_status=request.chain_status,
            last_verified_at=integrity["last_verified_at"] if file_backed else request.last_verified_at,
            metadata=safe_evidence_metadata({**(request.metadata or {}), **integrity["metadata"]}),
        )
        return self.store_evidence(
            evidence,
            actor=actor,
            action="evidence_added",
            detail="Evidence item attached.",
            metadata={"evidence_type": evidence.evidence_type, "source_event_id": evidence.source_event_id},
        )

    def store_evidence(
        self,
        evidence: CaseEvidence,
        *,
        actor: str = "system",
        action: str = "evidence_added",
        detail: str = "Evidence item attached.",
        metadata: dict[str, Any] | None = None,
    ) -> CaseEvidence:
        self._require_case(evidence.case_id)
        max_items = int(((self._config.get("evidence") or {}).get("max_items_per_case")) or 500)
        if self._repository.get_evidence(evidence.evidence_id) is None and len(self._repository.list_evidence(evidence.case_id)) >= max_items:
            raise ValueError(f"Case '{evidence.case_id}' reached the evidence limit ({max_items})")
        stored = self._repository.add_evidence(evidence)
        self._touch_case(evidence.case_id)
        self._record_case_audit(
            evidence.case_id,
            action=action,
            actor=actor,
            detail=detail,
            metadata=metadata or {"evidence_type": stored.evidence_type, "source_event_id": stored.source_event_id},
        )
        _increment_metric("case_evidence_items_total")
        return stored

    def get_evidence(self, evidence_id: str) -> CaseEvidence | None:
        return self._repository.get_evidence(evidence_id)

    def update_evidence(self, evidence_id: str, updates: dict[str, Any], actor: str = "system") -> CaseEvidence:
        evidence = self._repository.update_evidence(evidence_id, updates)
        self._touch_case(evidence.case_id)
        self._record_case_audit(
            evidence.case_id,
            action="evidence_updated",
            actor=actor,
            detail="Evidence metadata updated.",
            metadata={"evidence_id": evidence_id, "updated_fields": sorted(updates.keys())},
        )
        return evidence

    def list_evidence(self, case_id: str) -> list[CaseEvidence]:
        self._require_case(case_id)
        return self._repository.list_evidence(case_id)

    def add_note(self, case_id: str, payload: CaseNoteCreateRequest | dict[str, Any], actor: str = "system") -> CaseNote:
        self._require_case(case_id)
        request = payload if isinstance(payload, CaseNoteCreateRequest) else CaseNoteCreateRequest.model_validate(payload)
        note = CaseNote(
            case_id=case_id,
            note=self._safe_text(request.note),
            created_by=actor,
            metadata=safe_evidence_metadata(request.metadata),
        )
        stored = self._repository.add_note(note)
        self._touch_case(case_id)
        self._record_case_audit(case_id, action="note_added", actor=actor, detail="Operator note added.", metadata={})
        _increment_metric("case_notes_total")
        return stored

    def list_notes(self, case_id: str) -> list[CaseNote]:
        self._require_case(case_id)
        return self._repository.list_notes(case_id)

    def assign_case(self, case_id: str, assigned_to: str, actor: str = "system", reason: str = "") -> CaseRecord:
        self._require_case(case_id)
        assignment = CaseAssignment(case_id=case_id, assigned_to=assigned_to, assigned_by=actor, reason=self._safe_text(reason))
        updated = self._repository.update_case(case_id, {"assigned_to": assigned_to, "updated_at": assignment.assigned_at})
        self._record_case_audit(
            case_id,
            action="case_assigned",
            actor=actor,
            detail=f"Case assigned to {assigned_to}.",
            metadata=assignment.model_dump(mode="json"),
        )
        _increment_metric("cases_updated_total")
        return updated

    def close_case(self, case_id: str, actor: str = "system", reason: str = "") -> CaseRecord:
        current = self._require_case(case_id)
        self._validate_status_transition(current.status, "resolved")
        case = self._repository.update_case(case_id, {"status": "resolved", "updated_at": _now_iso(), "closed_at": _now_iso()})
        self._record_case_audit(case_id, action="status_changed", actor=actor, detail=self._safe_text(reason) or "Case resolved.", metadata={"to_status": "resolved"})
        _increment_metric("cases_closed_total")
        return case

    def reopen_case(self, case_id: str, actor: str = "system", reason: str = "") -> CaseRecord:
        current = self._require_case(case_id)
        self._validate_status_transition(current.status, "open")
        case = self._repository.update_case(case_id, {"status": "open", "updated_at": _now_iso(), "closed_at": None})
        self._record_case_audit(case_id, action="case_reopened", actor=actor, detail=self._safe_text(reason) or "Case reopened.", metadata={"to_status": "open"})
        _increment_metric("cases_reopened_total")
        return case

    def dismiss_case(self, case_id: str, actor: str = "system", reason: str = "") -> CaseRecord:
        current = self._require_case(case_id)
        self._validate_status_transition(current.status, "dismissed")
        case = self._repository.update_case(case_id, {"status": "dismissed", "updated_at": _now_iso(), "closed_at": _now_iso()})
        self._record_case_audit(case_id, action="case_dismissed", actor=actor, detail=self._safe_text(reason) or "Case dismissed.", metadata={"to_status": "dismissed"})
        _increment_metric("cases_dismissed_total")
        return case

    def archive_case(self, case_id: str, actor: str = "system", reason: str = "") -> CaseRecord:
        current = self._require_case(case_id)
        self._validate_status_transition(current.status, "archived")
        case = self._repository.update_case(case_id, {"status": "archived", "updated_at": _now_iso(), "closed_at": _now_iso()})
        self._record_case_audit(case_id, action="case_archived", actor=actor, detail=self._safe_text(reason) or "Case archived.", metadata={"to_status": "archived"})
        _increment_metric("cases_archived_total")
        return case

    def get_timeline(self, case_id: str):
        self._require_case(case_id)
        return self._timeline_service.build_timeline(case_id)

    def export_case(self, case_id: str, format: str = "json", actor: str = "system") -> CaseExport:
        export = self._export_service.export_case(case_id, format=format, generated_by=actor)
        self._record_case_audit(
            case_id,
            action="case_exported",
            actor=actor,
            detail=f"Case exported as {export.format}.",
            metadata={"format": export.format, "export_id": export.export_id},
        )
        _increment_metric("case_exports_total")
        return export

    def record_case_audit_event(
        self,
        case_id: str,
        *,
        action: str,
        actor: str,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> CaseAuditLog:
        return self._record_case_audit(case_id, action=action, actor=actor, detail=detail, metadata=metadata or {})

    def create_case_from_event_id(self, event_id: str, actor: str = "system") -> CaseRecord:
        payload = self.resolve_event_by_id(event_id)
        if payload is None:
            raise KeyError(event_id)
        result = self.create_or_attach_from_event(payload, actor=actor, force_create=True)
        if result is None:
            raise ValueError(f"Event '{event_id}' could not be normalized into a case")
        return result if isinstance(result, CaseRecord) else self._require_case(result.case_id)

    def create_or_attach_from_event(
        self,
        payload: Any,
        actor: str = "system",
        force_create: bool = False,
    ) -> CaseRecord | CaseEvidence | None:
        event = self._normalize_event_payload(payload)
        if event is None:
            return None
        if not force_create and not self._should_auto_create(event):
            return None

        related_case = self._find_related_case(event)
        if related_case is not None:
            evidence = self.add_evidence(
                related_case.case_id,
                {
                    "evidence_type": event["evidence_type"],
                    "title": event["title"],
                    "description": event["description"],
                    "source_event_id": event["event_id"],
                    "camera_id": event["camera_id"],
                    "track_ids": event["track_ids"],
                    "storage_uri": event.get("storage_uri"),
                    "snapshot_uri": event.get("snapshot_uri"),
                    "timestamp": event["timestamp"],
                    "metadata": event["metadata"],
                },
                actor=actor,
            )
            updates = {
                "source_event_ids": _merge_unique(related_case.source_event_ids, [event["event_id"]]),
                "camera_ids": _merge_unique(related_case.camera_ids, [event["camera_id"]] if event["camera_id"] else []),
                "track_ids": _merge_unique(related_case.track_ids, event["track_ids"]),
                "severity": _higher_severity(related_case.severity, event["severity"]),
                "priority": _higher_priority(related_case.priority, event["priority"]),
                "updated_at": _now_iso(),
                "metadata": {**(related_case.metadata or {}), "last_event_timestamp": event["timestamp"], "event_type": event["event_type"]},
            }
            self._repository.update_case(related_case.case_id, updates)
            self._record_case_audit(
                related_case.case_id,
                action="auto_deduplicated",
                actor=actor,
                detail="Related event merged into existing case.",
                metadata={"event_id": event["event_id"], "event_type": event["event_type"]},
            )
            _increment_metric("case_auto_dedup_total")
            return evidence

        case = self.create_case(
            {
                "title": event["title"],
                "description": event["description"],
                "priority": event["priority"],
                "severity": event["severity"],
                "source_event_ids": [event["event_id"]],
                "camera_ids": [event["camera_id"]] if event["camera_id"] else [],
                "track_ids": event["track_ids"],
                "tags": [event["event_type"], "requires-review"],
                "requires_review": True,
                "review_status": "pending",
                "metadata": {
                    **event["metadata"],
                    "auto_created": True,
                    "event_type": event["event_type"],
                    "last_event_timestamp": event["timestamp"],
                },
            },
            actor=actor,
        )
        self.add_evidence(
            case.case_id,
            {
                "evidence_type": event["evidence_type"],
                "title": event["title"],
                "description": event["description"],
                "source_event_id": event["event_id"],
                "camera_id": event["camera_id"],
                "track_ids": event["track_ids"],
                "storage_uri": event.get("storage_uri"),
                "snapshot_uri": event.get("snapshot_uri"),
                "timestamp": event["timestamp"],
                "metadata": event["metadata"],
            },
            actor=actor,
        )
        self._record_case_audit(
            case.case_id,
            action="event_linked",
            actor=actor,
            detail="Source event linked to case.",
            metadata={"event_id": event["event_id"], "event_type": event["event_type"]},
        )
        _increment_metric("cases_auto_created_total")
        return case

    def resolve_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        bus_records = get_event_bus().replay_recent(limit=2000)
        for record in reversed(bus_records):
            payload = _payload_to_dict(getattr(record, "payload", {}))
            identifiers = {
                str(event_id),
                str(getattr(record, "event_id", "")),
                str(payload.get("event_id", "")),
                str(payload.get("scan_id", "")),
                str(payload.get("window_id", "")),
                str(payload.get("match_id", "")),
            }
            if str(event_id) in identifiers:
                return {
                    "bus_event_type": getattr(record, "event_type", None),
                    "bus_event_id": getattr(record, "event_id", None),
                    "payload": payload,
                }

        try:
            from inference.identity_db import get_db

            for record in get_db().get_events(limit=2000):
                metadata = record.get("metadata", {}) or {}
                payload = _payload_to_dict(metadata.get("payload") or record)
                if str(event_id) in {str(record.get("event_id", "")), str(payload.get("event_id", ""))}:
                    return {"payload": payload, "bus_event_type": payload.get("event_type"), "bus_event_id": record.get("event_id")}
        except Exception:
            pass

        try:
            from inference.runtime import get_intelligence_runtime

            runtime = get_intelligence_runtime()
            ov_results = runtime.get_open_vocab_results(limit=500).get("items", [])
            for item in ov_results:
                if str(event_id) == str(item.get("scan_id", "")):
                    return {"payload": item, "bus_event_type": "open_vocab_scan_result", "bus_event_id": item.get("scan_id")}
            for item in runtime.get_live_anomalies():
                if str(event_id) == str(item.get("window_id", "")):
                    return {"payload": item, "bus_event_type": "anomaly_event", "bus_event_id": item.get("window_id")}
        except Exception:
            pass
        return None

    def health(self) -> dict[str, Any]:
        return self._repository.health()

    def _subscribe_event_bus(self) -> None:
        global _CASE_SERVICE_SUBSCRIBED
        if _CASE_SERVICE_SUBSCRIBED:
            return
        bus = get_event_bus()
        for event_type in (
            EventType.THREAT_EVENT,
            EventType.ANOMALY_EVENT,
            EventType.OPEN_VOCAB_SCAN_RESULT,
            EventType.WATCHLIST_HIT,
        ):
            bus.subscribe(event_type, self._on_bus_event)
        _CASE_SERVICE_SUBSCRIBED = True

    def _on_bus_event(self, record: Any) -> None:
        if not bool((self._config.get("auto_create") or {}).get("enabled", True)):
            return
        try:
            self.create_or_attach_from_event(record, actor="system")
        except Exception as exc:
            logger.warning("Case auto-create failed for bus event: %s", exc)
            _increment_metric("case_auto_create_failures_total")

    def _normalize_event_payload(self, payload: Any) -> dict[str, Any] | None:
        bus_event_type = None
        bus_event_id = None
        if hasattr(payload, "payload") and hasattr(payload, "event_type"):
            bus_event_type = getattr(payload, "event_type")
            bus_event_id = getattr(payload, "event_id", None)
            source = _payload_to_dict(getattr(payload, "payload", {}))
        elif isinstance(payload, dict) and "payload" in payload:
            bus_event_type = payload.get("bus_event_type") or payload.get("event_type")
            bus_event_id = payload.get("bus_event_id")
            source = _payload_to_dict(payload.get("payload") or payload)
        else:
            source = _payload_to_dict(payload)
            bus_event_type = source.get("event_type")

        normalized_type = _map_event_type(bus_event_type, source)
        if normalized_type is None:
            return None
        normalized_id = (
            str(source.get("event_id") or source.get("scan_id") or source.get("window_id") or source.get("match_id") or bus_event_id or "")
        )
        if not normalized_id:
            return None
        severity = _normalize_severity(source.get("severity") or source.get("highest_risk") or source.get("priority_level"))
        priority = _normalize_priority(source.get("priority_level") or severity)
        timestamp = str(source.get("timestamp") or source.get("scan_timestamp") or source.get("created_at") or _now_iso())
        camera_id = _first_non_empty(source.get("camera_id"), _first_from_list(source.get("camera_ids")))
        track_ids = [str(item) for item in (source.get("track_ids") or []) if str(item)]
        metadata = safe_evidence_metadata(
            {
                **source,
                "source_bus_event_id": bus_event_id,
                "source_bus_event_type": bus_event_type,
                "event_type": normalized_type,
            }
        )
        title = _AUTO_TITLES.get(normalized_type, "Possible incident")
        description = _auto_description(normalized_type, source)
        return {
            "event_id": normalized_id,
            "event_type": normalized_type,
            "severity": severity,
            "priority": priority,
            "timestamp": timestamp,
            "camera_id": camera_id,
            "track_ids": track_ids,
            "title": title,
            "description": description,
            "metadata": metadata,
            "evidence_type": _EVIDENCE_TYPE_BY_EVENT.get(normalized_type, "event"),
            "storage_uri": source.get("storage_uri") or source.get("image_path"),
            "snapshot_uri": source.get("snapshot_uri") or source.get("annotated_image_url"),
        }

    def _should_auto_create(self, event: dict[str, Any]) -> bool:
        auto_cfg = dict(self._config.get("auto_create") or {})
        if not bool(auto_cfg.get("enabled", True)):
            return False
        allowed_types = {str(item).lower() for item in (auto_cfg.get("event_types") or [])}
        if event["event_type"] not in allowed_types:
            return False
        min_severity = _normalize_severity(auto_cfg.get("min_severity") or "high")
        return _SEVERITY_ORDER.get(event["severity"], 0) >= _SEVERITY_ORDER.get(min_severity, 0)

    def _find_related_case(self, event: dict[str, Any]) -> CaseRecord | None:
        dedup_cfg = dict(self._config.get("deduplication") or {})
        if not bool(dedup_cfg.get("enabled", True)):
            return None
        window_seconds = int(dedup_cfg.get("window_seconds") or 300)
        now_ts = _parse_timestamp(event["timestamp"])
        open_cases = self._repository.list_cases({"status": ["open", "investigating"], "limit": 500})
        for case in open_cases:
            case_ts = _parse_timestamp((case.metadata or {}).get("last_event_timestamp") or case.updated_at or case.created_at)
            if case_ts and abs(now_ts - case_ts) > window_seconds:
                continue
            if bool(dedup_cfg.get("same_event_type_merge", True)):
                existing_type = str((case.metadata or {}).get("event_type", "")).lower()
                if existing_type and existing_type != event["event_type"]:
                    continue
            if bool(dedup_cfg.get("same_camera_merge", True)) and event["camera_id"]:
                if event["camera_id"] not in case.camera_ids:
                    continue
            if bool(dedup_cfg.get("same_track_merge", True)) and event["track_ids"]:
                if not set(event["track_ids"]) & set(case.track_ids):
                    continue
            return case
        return None

    def _validate_status_transition(self, current_status: str, next_status: str) -> None:
        if next_status not in CASE_STATUSES:
            raise ValueError(f"Unsupported case status '{next_status}'")
        if current_status == next_status:
            return
        allowed = _ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
        if next_status not in allowed:
            raise ValueError(f"Invalid case status transition: {current_status} -> {next_status}")

    def _build_integrity_payload(self, storage_uri: str | None) -> dict[str, Any]:
        if not storage_uri:
            return {
                "hash_sha256": None,
                "hash_verified": None,
                "integrity_status": "not_applicable",
                "size_bytes": None,
                "content_type": None,
                "safe_filename": None,
                "original_filename": None,
                "last_verified_at": None,
                "metadata": {},
            }
        resolved = resolve_local_storage_uri(storage_uri)
        artifact = describe_local_artifact(
            storage_uri,
            allowed_roots=[resolved.parent] if resolved is not None else None,
            content_type=guess_content_type(storage_uri),
        )
        path = artifact.get("path")
        return {
            "hash_sha256": artifact.get("hash_sha256"),
            "hash_verified": artifact.get("hash_verified"),
            "integrity_status": artifact.get("integrity_status"),
            "size_bytes": artifact.get("size_bytes"),
            "content_type": artifact.get("content_type"),
            "safe_filename": artifact.get("safe_filename"),
            "original_filename": path.name if isinstance(path, Path) else None,
            "last_verified_at": artifact.get("last_verified_at"),
            "metadata": {
                "missing_evidence": artifact.get("integrity_status") == "missing_file",
                **({"missing_path": str(path)} if artifact.get("integrity_status") == "missing_file" and isinstance(path, Path) else {}),
            },
        }

    def _touch_case(self, case_id: str) -> None:
        case = self._repository.get_case(case_id)
        if case is None:
            return
        self._repository.update_case(case_id, {"updated_at": _now_iso()})

    def _require_case(self, case_id: str) -> CaseRecord:
        case = self._repository.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        return case

    def _ensure_available(self) -> None:
        if not self._repository.is_available():
            raise RuntimeError(self._repository.health().get("last_error") or "Case storage is unavailable")

    def _record_case_audit(
        self,
        case_id: str,
        action: str,
        actor: str,
        detail: str,
        metadata: dict[str, Any],
    ) -> CaseAuditLog:
        audit = CaseAuditLog(
            case_id=case_id,
            action=action,
            actor=actor,
            detail=self._safe_text(detail),
            metadata=safe_evidence_metadata(metadata),
        )
        return self._repository.add_audit_log(audit)

    def _merge_tags(self, tags: list[str], metadata: dict[str, Any]) -> list[str]:
        defaults = ["requires-review"] if metadata.get("auto_created") else []
        return _merge_unique(tags, defaults)

    def _safe_text(self, text: str | None) -> str:
        cleaned = str(text or "").strip()
        lowered = cleaned.lower()
        for forbidden, replacement in _FORBIDDEN_PHRASES.items():
            if forbidden in lowered:
                cleaned = replacement
                lowered = cleaned.lower()
        return cleaned


def _payload_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _map_event_type(bus_event_type: Any, payload: dict[str, Any]) -> str | None:
    raw_bus_type = getattr(bus_event_type, "value", bus_event_type)
    event_label = str(payload.get("event_type") or raw_bus_type or "").lower()
    if event_label == "open_vocab_scan_result" or "open_vocab" in event_label:
        return "open_vocab_scan_result"
    if str(raw_bus_type or "").lower() == EventType.WATCHLIST_HIT.value.lower() or payload.get("match_id") or payload.get("identity_id"):
        return "identity_match"
    anomaly_type = str(payload.get("anomaly_type") or "").lower()
    if anomaly_type == "restricted_zone":
        return "restricted_zone_intrusion"
    if str(raw_bus_type or "").lower() == EventType.ANOMALY_EVENT.value.lower() or anomaly_type:
        return "anomaly_event"
    if "restricted_zone" in event_label or "geofence" in event_label:
        return "restricted_zone_intrusion"
    if any(term in event_label.upper() for term in ("WEAPON", "GUN", "KNIFE", "RIFLE", "PISTOL", "GRENADE", "SHOTGUN")):
        return "weapon_detected"
    return None


def _normalize_severity(value: Any) -> str:
    text = str(value or "medium").lower()
    if text in CASE_SEVERITIES:
        return text
    if text in {"critical", "crit"}:
        return "critical"
    if text in {"high", "severe"}:
        return "high"
    if text in {"medium", "moderate"}:
        return "medium"
    return "low"


def _normalize_priority(value: Any) -> str:
    text = str(value or "medium").lower()
    if text in CASE_PRIORITIES:
        return text
    return _normalize_severity(text)


def _higher_severity(left: str, right: str) -> str:
    return right if _SEVERITY_ORDER.get(right, 0) > _SEVERITY_ORDER.get(left, 0) else left


def _higher_priority(left: str, right: str) -> str:
    return _higher_severity(left, right)


def _auto_description(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "weapon_detected":
        return "Possible weapon-related event detected. Operator review required."
    if event_type == "open_vocab_scan_result":
        return "Possible open-vocabulary detection requires operator review."
    if event_type == "anomaly_event":
        label = payload.get("display_label") or "Possible anomaly"
        return f"{label}. Operator review required."
    if event_type == "identity_match":
        return "Possible identity match observed. Operator validation required."
    if event_type == "restricted_zone_intrusion":
        return "Possible restricted-zone incident observed. Operator review required."
    return "Possible incident requires operator review."


def _first_from_list(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and value:
        first = str(value[0]).strip()
        return first or None
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _merge_unique(left: list[str] | None, right: list[str] | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in (left or [], right or []):
        if not group:
            continue
        if isinstance(group, str):
            values = [group]
        else:
            values = list(group)
        for item in values:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _parse_timestamp(value: str | None) -> float:
    from app.repositories.case_repository import _parse_timestamp as _repo_parse_timestamp

    return _repo_parse_timestamp(value)


def _increment_metric(name: str, count: int = 1) -> None:
    try:
        from inference.monitoring.metrics import get_metrics

        get_metrics().increment(name, count)
    except Exception:
        pass
    try:
        from inference.metrics import metrics as system_metrics

        system_metrics.increment(name, count)
    except Exception:
        pass


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def get_case_service() -> CaseService:
    global _CASE_SERVICE
    if _CASE_SERVICE is None:
        _CASE_SERVICE = CaseService()
    return _CASE_SERVICE


def reset_case_service() -> None:
    global _CASE_SERVICE, _CASE_SERVICE_SUBSCRIBED
    _CASE_SERVICE = None
    _CASE_SERVICE_SUBSCRIBED = False
