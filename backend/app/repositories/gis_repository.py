from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.models.gis_models import (
    CameraGeoProfile,
    CaseGeoMarker,
    EventGeoMarker,
    GeoFenceZone,
    NearbyCameraResult,
    RiskHeatmapCell,
)
from app.models.security_models import UserAccount
from app.api.object_authorization import (
    can_access_camera,
    can_access_case,
    can_access_event_payload,
    can_access_incident,
    can_access_uploaded_video_session,
)
from app.security.config import PROJECT_ROOT
from app.services.case_service import get_case_service
from app.services.uploaded_video_service import get_uploaded_video_service
from app.repositories.incident_repository import get_incident_repository
from inference.config_runtime import load_runtime_config


def _camera_profiles_path() -> Path:
    cfg = load_runtime_config("gis").get("gis") or {}
    storage = cfg.get("storage") or {}
    return PROJECT_ROOT / str(storage.get("dev_camera_profiles_path") or "storage/gis/camera_geo_profiles.jsonl")


def _geofences_path() -> Path:
    cfg = load_runtime_config("gis").get("gis") or {}
    storage = cfg.get("storage") or {}
    return PROJECT_ROOT / str(storage.get("dev_geofences_path") or "storage/gis/geofences.jsonl")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else "")
    path.write_text(text, encoding="utf-8")


def _now_ts() -> float:
    return time.time()


def _parse_time(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        if text.replace(".", "", 1).isdigit():
            return float(text)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except (ValueError, OSError):
        return None


def _iso_from_ts(ts: float | None) -> str:
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


@dataclass
class GisRepository:
    """JSONL-backed GIS store with object-scope filtering for development."""

    def get_camera_geo_profile(self, camera_id: str) -> CameraGeoProfile | None:
        for row in _read_jsonl(_camera_profiles_path()):
            if str(row.get("camera_id")) == camera_id:
                return CameraGeoProfile.model_validate(row)
        return None

    def upsert_camera_geo_profile(self, profile: CameraGeoProfile) -> CameraGeoProfile:
        path = _camera_profiles_path()
        rows = _read_jsonl(path)
        out: list[dict[str, Any]] = []
        replaced = False
        payload = profile.model_dump(mode="json")
        for row in rows:
            if str(row.get("camera_id")) == profile.camera_id:
                out.append(payload)
                replaced = True
            else:
                out.append(row)
        if not replaced:
            out.append(payload)
        _write_jsonl(path, out)
        return profile

    def list_camera_geo_profiles(self, user: UserAccount | None) -> list[CameraGeoProfile]:
        items: list[CameraGeoProfile] = []
        for row in _read_jsonl(_camera_profiles_path()):
            try:
                profile = CameraGeoProfile.model_validate(row)
            except Exception:
                continue
            if not can_access_camera(user, profile.camera_id):
                continue
            items.append(profile)
        return items

    def create_geofence(self, zone: GeoFenceZone) -> GeoFenceZone:
        path = _geofences_path()
        rows = _read_jsonl(path)
        rows.append(zone.model_dump(mode="json"))
        _write_jsonl(path, rows)
        return zone

    def update_geofence(self, zone_id: str, update: dict[str, Any]) -> GeoFenceZone | None:
        path = _geofences_path()
        rows = _read_jsonl(path)
        found: dict[str, Any] | None = None
        rest: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("zone_id")) == zone_id:
                found = dict(row)
            else:
                rest.append(row)
        if found is None:
            return None
        found.update({k: v for k, v in update.items() if v is not None})
        rest.append(found)
        _write_jsonl(path, rest)
        return GeoFenceZone.model_validate(found)

    def delete_geofence(self, zone_id: str) -> bool:
        path = _geofences_path()
        rows = _read_jsonl(path)
        kept = [r for r in rows if str(r.get("zone_id")) != zone_id]
        if len(kept) == len(rows):
            return False
        _write_jsonl(path, kept)
        return True

    def list_geofences(self, user: UserAccount | None) -> list[GeoFenceZone]:
        del user
        zones: list[GeoFenceZone] = []
        for row in _read_jsonl(_geofences_path()):
            try:
                zones.append(GeoFenceZone.model_validate(row))
            except Exception:
                continue
        return zones

    def get_geofence(self, zone_id: str) -> GeoFenceZone | None:
        for row in _read_jsonl(_geofences_path()):
            if str(row.get("zone_id")) == zone_id:
                return GeoFenceZone.model_validate(row)
        return None

    def get_event_markers(
        self,
        *,
        user: UserAccount | None,
        start_time: str | None = None,
        end_time: str | None = None,
        severity: str | None = None,
        event_type: str | None = None,
        camera_id: str | None = None,
        case_id: str | None = None,
        source_type: str | None = None,
    ) -> list[EventGeoMarker]:
        cfg = load_runtime_config("gis").get("gis") or {}
        ev_cfg = cfg.get("events") or {}
        max_age_h = float(ev_cfg.get("max_marker_age_hours", 72))
        t0 = _parse_time(start_time) or (_now_ts() - max_age_h * 3600.0)
        t1 = _parse_time(end_time) or _now_ts()
        profiles = {p.camera_id: p for p in self.list_camera_geo_profiles(user)}
        markers: list[EventGeoMarker] = []

        try:
            from inference.runtime import get_intelligence_runtime

            runtime = get_intelligence_runtime()
        except Exception:
            runtime = None

        if runtime is not None:
            for incident in runtime.get_incidents():
                iid = str(incident.get("incident_id") or "")
                if not iid or not can_access_incident(user, iid):
                    continue
                ts = float(incident.get("updated_at") or incident.get("created_at") or _now_ts())
                if ts < t0 or ts > t1:
                    continue
                cams = [str(c) for c in incident.get("camera_ids") or []]
                primary = cams[0] if cams else None
                if camera_id and primary != camera_id:
                    continue
                if case_id:
                    continue
                sev = str(incident.get("severity") or "medium")
                if severity and sev != severity:
                    continue
                et = str(incident.get("incident_type") or "possible_incident")
                if event_type and et != event_type:
                    continue
                if source_type and source_type != "live_stream":
                    continue
                if not primary or primary not in profiles:
                    continue
                prof = profiles[primary]
                markers.append(
                    EventGeoMarker(
                        event_id=iid,
                        source_type="live_stream",
                        camera_id=primary,
                        case_id=None,
                        event_type=et,
                        severity=sev,
                        latitude=prof.latitude,
                        longitude=prof.longitude,
                        timestamp=_iso_from_ts(ts),
                        risk_score=float(incident.get("risk_score") or 0.0) * 100.0 if incident.get("risk_score") is not None else None,
                        operator_review_required=True,
                        title="Possible incident — operator review required",
                    )
                )

            for anomaly in runtime.get_live_anomalies():
                if not can_access_event_payload(user, anomaly):
                    continue
                ts = float(anomaly.get("timestamp") or _now_ts())
                if ts < t0 or ts > t1:
                    continue
                cam = str(anomaly.get("camera_id") or "")
                if camera_id and cam != camera_id:
                    continue
                if not cam or cam not in profiles:
                    continue
                prof = profiles[cam]
                et = str(anomaly.get("event_type") or "anomaly_event")
                if event_type and et != event_type:
                    continue
                sev = str(anomaly.get("severity") or "medium")
                if severity and str(sev) != severity:
                    continue
                if source_type and source_type != "live_stream":
                    continue
                markers.append(
                    EventGeoMarker(
                        event_id=str(anomaly.get("event_id") or anomaly.get("id") or f"anom_{cam}_{int(ts)}"),
                        source_type="live_stream",
                        camera_id=cam,
                        case_id=None,
                        event_type=et,
                        severity=sev if sev in {"low", "medium", "high", "critical"} else "medium",
                        latitude=prof.latitude,
                        longitude=prof.longitude,
                        timestamp=_iso_from_ts(ts),
                        risk_score=float(anomaly.get("risk_score") or anomaly.get("severity") or 0.0),
                        operator_review_required=True,
                        title="Possible incident — operator review required",
                    )
                )

        if (source_type is None or source_type == "uploaded_video") and bool(ev_cfg.get("show_uploaded_video_events", True)):
            try:
                sessions = get_uploaded_video_service().list_sessions()
            except Exception:
                sessions = []
            for session in sessions:
                sid = str(session.session_id)
                if not can_access_uploaded_video_session(user, sid):
                    continue
                meta = dict(session.metadata or {})
                lat = meta.get("demo_latitude") or meta.get("latitude")
                lon = meta.get("demo_longitude") or meta.get("longitude")
                link_cam = str(meta.get("linked_camera_id") or "").strip()
                prof = profiles.get(link_cam) if link_cam else None
                if lat is None or lon is None:
                    if prof is None:
                        continue
                    lat, lon = prof.latitude, prof.longitude
                else:
                    lat, lon = float(lat), float(lon)
                created = _parse_time(session.created_at) or _now_ts()
                if created < t0 or created > t1:
                    continue
                markers.append(
                    EventGeoMarker(
                        event_id=sid,
                        source_type="uploaded_video",
                        camera_id=link_cam or None,
                        case_id=session.linked_case_id,
                        event_type="uploaded_video_session",
                        severity="medium",
                        latitude=float(lat),
                        longitude=float(lon),
                        timestamp=session.created_at,
                        risk_score=None,
                        operator_review_required=True,
                        title="Uploaded video analysis — operator review required",
                    )
                )

        if source_type in {None, "drone_simulation"}:
            try:
                records = get_incident_repository().list_events(
                    {
                        "source_type": "drone_simulation",
                        "camera_id": camera_id,
                        "case_id": case_id,
                        "event_type": event_type,
                        "severity": severity,
                        "limit": 500,
                    }
                )
            except Exception:
                records = []
            for record in records:
                payload = dict(record.metadata or {})
                lat = payload.get("latitude")
                lon = payload.get("longitude")
                if lat is None or lon is None:
                    prof = profiles.get(record.camera_id or "")
                    if prof is None:
                        continue
                    lat = prof.latitude
                    lon = prof.longitude
                access_payload = {
                    "source_type": "drone_simulation",
                    "camera_id": record.camera_id,
                    "camera_ids": [record.camera_id] if record.camera_id else [],
                    "incident_id": record.event_id,
                }
                if not can_access_event_payload(user, access_payload):
                    continue
                ts = _parse_time(record.timestamp) or _now_ts()
                if ts < t0 or ts > t1:
                    continue
                markers.append(
                    EventGeoMarker(
                        event_id=record.event_id,
                        source_type="drone_simulation",
                        camera_id=record.camera_id,
                        case_id=record.case_id,
                        event_type=record.event_type,
                        severity=record.severity,
                        latitude=float(lat),
                        longitude=float(lon),
                        altitude_meters=payload.get("altitude_meters"),
                        timestamp=record.timestamp,
                        risk_score=float(record.risk_score or 0.0),
                        operator_review_required=True,
                        title=str(payload.get("safe_label") or "Simulated aerial observation"),
                        metadata=payload,
                    )
                )

        return markers

    def get_case_markers(
        self,
        *,
        user: UserAccount | None,
        start_time: str | None,
        end_time: str | None,
        severity: str | None,
        camera_id: str | None,
        case_id: str | None,
    ) -> list[CaseGeoMarker]:
        t0 = _parse_time(start_time)
        t1 = _parse_time(end_time)
        profiles = {p.camera_id: p for p in self.list_camera_geo_profiles(user)}
        service = get_case_service()
        markers: list[CaseGeoMarker] = []
        for case in service.list_cases({"limit": 5000}):
            if not can_access_case(user, case.case_id):
                continue
            if case_id and case.case_id != case_id:
                continue
            if severity and str(case.severity) != severity:
                continue
            if camera_id and camera_id not in {str(c) for c in case.camera_ids}:
                continue
            primary: str | None = None
            for cid in case.camera_ids:
                cid = str(cid)
                if cid in profiles:
                    primary = cid
                    break
            meta = dict(case.metadata or {})
            if primary is None:
                if meta.get("manual_latitude") is not None and meta.get("manual_longitude") is not None:
                    lat = float(meta["manual_latitude"])
                    lon = float(meta["manual_longitude"])
                else:
                    continue
            else:
                prof = profiles[primary]
                lat, lon = prof.latitude, prof.longitude
            updated = _parse_time(case.updated_at)
            if t0 is not None and updated is not None and updated < t0:
                continue
            if t1 is not None and updated is not None and updated > t1:
                continue
            markers.append(
                CaseGeoMarker(
                    case_id=case.case_id,
                    title=case.title,
                    severity=str(case.severity),
                    latitude=lat,
                    longitude=lon,
                    primary_camera_id=primary,
                    updated_at=case.updated_at,
                    operator_review_required=bool(case.requires_review),
                )
            )
        return markers

    def count_camera_profiles(self) -> int:
        return len(_read_jsonl(_camera_profiles_path()))

    def count_geofences(self) -> int:
        return len(_read_jsonl(_geofences_path()))

    def find_nearby_cameras(
        self,
        user: UserAccount | None,
        latitude: float,
        longitude: float,
        radius_meters: float,
    ) -> list[NearbyCameraResult]:
        from app.services.gis_service import find_nearby_cameras as _find

        return _find(self, user, latitude, longitude, radius_meters)

    def compute_risk_heatmap(
        self,
        user: UserAccount | None,
        start_time: str | None,
        end_time: str | None,
        severity: str | None,
        event_type: str | None,
        camera_id: str | None,
        case_id: str | None,
        source_type: str | None,
    ) -> list[RiskHeatmapCell]:
        from app.services.gis_service import compute_risk_heatmap as _heat

        return _heat(self, user, start_time, end_time, severity, event_type, camera_id, case_id, source_type)


_repo: GisRepository | None = None


def reset_gis_repository_singleton() -> None:
    """Test helper — clears cached GIS repository (paths may be monkeypatched)."""
    global _repo
    _repo = None


def get_gis_repository() -> GisRepository:
    global _repo
    if _repo is None:
        _repo = GisRepository()
    return _repo


def new_zone_id() -> str:
    return f"zone_{uuid.uuid4().hex[:12]}"
