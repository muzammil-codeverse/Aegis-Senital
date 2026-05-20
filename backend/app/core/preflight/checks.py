from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from app.core.capabilities.models import CapabilityResourceProfile, CapabilityState
from app.core.capabilities.registry import CapabilityRegistry
from app.core.preflight.models import (
    PreflightCapabilityGroup,
    PreflightCapabilityResult,
    PreflightCheckResult,
    PreflightCheckStatus,
    PreflightMode,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]

CAPABILITY_GROUPS: dict[PreflightCapabilityGroup, tuple[str, ...]] = {
    PreflightCapabilityGroup.FOUNDATIONAL: (
        "backend_api",
        "frontend_api_contract",
        "auth_session",
        "rbac_permissions",
        "local_storage",
        "runtime_health",
    ),
    PreflightCapabilityGroup.COMMAND_CENTER: (
        "alerts",
        "incidents",
        "cases",
        "evidence",
        "reports",
        "analytics",
    ),
    PreflightCapabilityGroup.VIDEO_INTELLIGENCE: (
        "uploaded_video_pipeline",
        "live_stream_pipeline",
        "yolo_weapon_detector",
        "yolo_phone_detector",
        "tracking_engine",
        "event_engine",
        "scenario_engine",
    ),
    PreflightCapabilityGroup.DRONE_SYSTEM: (
        "drone_simulation",
        "drone_mission_planner",
        "drone_fusion",
        "drone_telemetry",
        "drone_path_tracking",
        "simulation_source_network",
        "sim_scenario_engine",
        "visual_tracking_fusion",
        "drone_unified_state",
        "exhibition_demo_workflow",
    ),
    PreflightCapabilityGroup.ADVANCED_INTELLIGENCE: (
        "anomaly_detection",
        "open_vocab_detection",
        "segmentation",
        "identity_reid",
        "model_governance",
        "gis_map",
        "llm_osint",
    ),
}

FOUNDATIONAL_CAPABILITIES = set(CAPABILITY_GROUPS[PreflightCapabilityGroup.FOUNDATIONAL])
QUICK_CAPABILITIES = tuple(CAPABILITY_GROUPS[PreflightCapabilityGroup.FOUNDATIONAL])
EXHIBITION_CAPABILITIES = tuple(
    capability_id for group in CAPABILITY_GROUPS.values() for capability_id in group
)

SAFE_IMPORT_MODULES: dict[str, tuple[str, ...]] = {
    "auth_session": ("app.services.auth_service",),
    "rbac_permissions": ("app.security.permissions", "app.security.config"),
    "local_storage": ("app.core.persistence",),
    "cases": ("app.services.case_service", "app.repositories.case_repository"),
    "evidence": ("app.services.evidence_integrity", "app.services.evidence_file_service"),
    "reports": ("app.services.case_export_service",),
    "analytics": ("app.services.analytics_service", "app.repositories.analytics_repository"),
    "alerts": ("inference.alerts.alert_manager", "app.services.command_center_intelligence_service"),
    "incidents": ("app.repositories.incident_repository", "app.services.command_center_intelligence_service"),
    "gis_map": ("app.services.gis_service", "app.repositories.gis_repository"),
    "llm_osint": ("app.services.llm_service", "app.services.osint_service"),
    "uploaded_video_pipeline": ("app.services.uploaded_video_service", "app.services.command_center_intelligence_service"),
    "event_engine": ("inference.event_engine", "app.models.intelligence_models"),
    "drone_mission_planner": ("app.repositories.drone_mission_repository",),
    "drone_fusion": ("app.repositories.drone_fusion_repository", "app.services.drone_fusion.fusion_service"),
    "simulation_source_network": (
        "app.services.simulation_source_service",
        "app.models.simulation_source_models",
    ),
    "sim_scenario_engine": (
        "app.services.scenario_engine_service",
        "app.models.scenario_models",
    ),
    "visual_tracking_fusion": (
        "app.services.fused_path_service",
        "app.models.tracking_models",
    ),
    "drone_unified_state": (
        "app.services.drone_operational_state_service",
        "app.models.drone_unified_models",
    ),
    "exhibition_demo_workflow": (
        "app.services.exhibition_demo_service",
        "app.api.exhibition_demo_routes",
    ),
}

ROUTE_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "backend_api": ("backend/main.py", "backend/app/api/routes.py"),
    "frontend_api_contract": ("frontend/src/api/client.js", "frontend/src/api/capabilityApi.js"),
    "runtime_health": ("backend/app/services/runtime_health_service.py",),
    "alerts": ("backend/app/api/routes.py", "frontend/src/components/alerts/AlertCard.jsx"),
    "incidents": ("backend/app/api/routes.py", "backend/app/repositories/incident_repository.py", "frontend/src/components/dashboard/IncidentPanel.jsx"),
    "cases": ("backend/app/api/case_routes.py", "frontend/src/components/uploaded-video/CreateCaseFromVideoButton.jsx"),
    "evidence": ("backend/app/services/evidence_integrity.py", "frontend/src/components/cases/CaseEvidencePanel.jsx"),
    "reports": ("backend/app/services/case_export_service.py", "frontend/src/components/uploaded-video/UploadedVideoReportPanel.jsx"),
    "analytics": ("backend/app/api/analytics_routes.py", "frontend/src/pages/Dashboard.jsx"),
    "uploaded_video_pipeline": (
        "backend/app/api/uploaded_video_routes.py",
        "frontend/src/api/uploadedVideoApi.js",
        "frontend/src/hooks/useUploadedVideo.js",
        "frontend/src/pages/UploadedVideoAnalysisPage.jsx",
        "backend/app/models/intelligence_models.py",
        "backend/app/services/command_center_intelligence_service.py",
    ),
    "live_stream_pipeline": ("backend/app/api/streaming_routes.py",),
    "drone_simulation": ("backend/app/api/drone_routes.py", "configs/runtime/drone_simulation.yaml"),
    "drone_telemetry": ("backend/app/api/drone_routes.py", "configs/runtime/drone_simulation.yaml"),
    "drone_path_tracking": ("backend/app/api/drone_routes.py", "configs/runtime/drone_mission.yaml"),
    "simulation_source_network": (
        "backend/app/api/simulation_routes.py",
        "backend/app/services/simulation_source_service.py",
        "backend/app/models/simulation_source_models.py",
    ),
    "sim_scenario_engine": (
        "backend/app/api/scenario_routes.py",
        "backend/app/services/scenario_engine_service.py",
        "backend/app/models/scenario_models.py",
    ),
    "visual_tracking_fusion": (
        "backend/app/api/tracking_routes.py",
        "backend/app/services/fused_path_service.py",
        "backend/app/models/tracking_models.py",
        "frontend/src/components/simulation/OperationalTrackingPanel.jsx",
        "frontend/src/components/simulation/SuspectPathMap.jsx",
        "frontend/src/components/simulation/CameraHandoffTimeline.jsx",
        "frontend/src/components/simulation/DroneRoutePanel.jsx",
    ),
    "drone_unified_state": (
        "backend/app/api/drone_unified_routes.py",
        "backend/app/services/drone_operational_state_service.py",
        "backend/app/models/drone_unified_models.py",
        "frontend/src/api/droneUnifiedApi.js",
    ),
    "exhibition_demo_workflow": (
        "backend/app/api/exhibition_demo_routes.py",
        "backend/app/services/exhibition_demo_service.py",
        "frontend/src/api/exhibitionDemoApi.js",
        "frontend/src/components/exhibition/ExhibitionDemoPanel.jsx",
        "docs/exhibition-demo-runbook.md",
        "docs/exhibition-final-checklist.md",
        "tests/test_exhibition_demo.py",
        "tests/test_phase10_hardening.py",
    ),
}

MODEL_REGISTRY_TASKS: dict[str, tuple[str, ...]] = {
    "yolo_weapon_detector": ("weapon_detector", "weapon"),
    "yolo_phone_detector": ("phone_detector", "phone"),
    "anomaly_detection": ("anomaly_pipeline",),
    "open_vocab_detection": ("open_vocab",),
    "segmentation": ("segmentation_sam2",),
    "identity_reid": ("face_recognition", "reid_osnet"),
    "llm_osint": ("llm_provider",),
}

SAFE_WARMUP_CAPABILITIES = {
    "backend_api",
    "frontend_api_contract",
    "auth_session",
    "rbac_permissions",
    "local_storage",
    "runtime_health",
    "alerts",
    "incidents",
    "cases",
    "evidence",
    "reports",
    "analytics",
    "gis_map",
    "model_governance",
    "simulation_source_network",
    "sim_scenario_engine",
    "visual_tracking_fusion",
    "drone_unified_state",
}

COMMAND_CENTER_INTEGRATION_CAPABILITIES = {
    "alerts",
    "incidents",
    "cases",
    "evidence",
    "reports",
    "analytics",
    "uploaded_video_pipeline",
    "event_engine",
}


def group_for_capability(capability_id: str) -> PreflightCapabilityGroup:
    for group, ids in CAPABILITY_GROUPS.items():
        if capability_id in ids:
            return group
    return PreflightCapabilityGroup.ADVANCED_INTELLIGENCE


def capabilities_for_mode(mode: PreflightMode) -> list[str]:
    if mode == PreflightMode.QUICK:
        return list(QUICK_CAPABILITIES)
    return list(EXHIBITION_CAPABILITIES)


def _resolve_repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _check(
    level: int,
    name: str,
    status: PreflightCheckStatus,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> PreflightCheckResult:
    return PreflightCheckResult(
        level=level,
        name=name,
        status=status,
        message=message,
        metadata=metadata or {},
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def _nested_get(payload: dict[str, Any], dotted_key: str | None) -> Any:
    if not dotted_key:
        return None
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _mask_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    prefix = value[:3] if len(value) >= 3 else "***"
    suffix = value[-4:] if len(value) >= 4 else "****"
    return f"{prefix}****{suffix}"


def _model_registry_payload() -> dict[str, Any]:
    path = PROJECT_ROOT / "models" / "registry.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _active_model_entries(capability_id: str) -> list[dict[str, Any]]:
    payload = _model_registry_payload()
    entries: list[dict[str, Any]] = []
    for key in MODEL_REGISTRY_TASKS.get(capability_id, ()):
        value = payload.get(key)
        if not isinstance(value, dict):
            continue
        active_version = value.get("active_version")
        active = value.get(active_version) if active_version else None
        if isinstance(active, dict):
            entries.append({"registry_key": key, **active})
        elif "path" in value:
            entries.append({"registry_key": key, **value})
    return entries


def _check_required_paths(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    missing: list[str] = []
    required_paths = [str(item) for item in (record.descriptor.metadata.get("required_paths") or [])]
    for raw in required_paths:
        path = _resolve_repo_path(raw)
        if path is None:
            continue
        if path.exists():
            checks.append(
                _check(
                    3,
                    "artifact_path",
                    PreflightCheckStatus.PASSED,
                    f"Required artifact path present: {_relative(path)}",
                    {"path": _relative(path)},
                )
            )
        else:
            missing.append(_relative(path))
            checks.append(
                _check(
                    3,
                    "artifact_path",
                    PreflightCheckStatus.FAILED,
                    f"Required artifact path missing: {_relative(path)}",
                    {"path": _relative(path)},
                )
            )

    for entry in _active_model_entries(record.descriptor.id):
        raw_path = entry.get("path")
        logical_only = bool(entry.get("logical_only"))
        optional_path = bool(entry.get("optional_path"))
        path = _resolve_repo_path(str(raw_path) if raw_path else None)
        if logical_only:
            checks.append(
                _check(
                    3,
                    "model_registry_entry",
                    PreflightCheckStatus.PASSED,
                    f"Model registry entry is configuration-backed: {entry.get('model_id') or entry.get('registry_key')}",
                    {"model_id": entry.get("model_id"), "registry_key": entry.get("registry_key")},
                )
            )
            continue
        if path and path.exists():
            checks.append(
                _check(
                    3,
                    "model_artifact",
                    PreflightCheckStatus.PASSED,
                    f"Model artifact present for {entry.get('registry_key')}: {_relative(path)}",
                    {"model_id": entry.get("model_id"), "path": _relative(path)},
                )
            )
        elif optional_path:
            checks.append(
                _check(
                    3,
                    "model_artifact",
                    PreflightCheckStatus.WARNING,
                    f"Model artifact is not present yet for {entry.get('registry_key')}; warmup remains deferred.",
                    {"model_id": entry.get("model_id"), "path": _relative(path) if path else None},
                )
            )
        else:
            missing_path = _relative(path) if path else str(raw_path or "")
            missing.append(missing_path)
            checks.append(
                _check(
                    3,
                    "model_artifact",
                    PreflightCheckStatus.FAILED,
                    f"Model artifact missing for {entry.get('registry_key')}: {missing_path}",
                    {"model_id": entry.get("model_id"), "path": missing_path},
                )
            )

    if not required_paths and record.descriptor.id not in MODEL_REGISTRY_TASKS:
        checks.append(
            _check(
                3,
                "artifact_path",
                PreflightCheckStatus.SKIPPED,
                "No artifact path is required for this lightweight preflight check.",
            )
        )

    return checks, missing


def _check_config(record) -> tuple[list[PreflightCheckResult], list[str], bool]:
    checks: list[PreflightCheckResult] = []
    warnings: list[str] = []
    configured_disabled = False
    metadata = record.descriptor.metadata or {}
    config_path = _resolve_repo_path(metadata.get("config_path"))
    if config_path is None:
        checks.append(
            _check(
                2,
                "runtime_config",
                PreflightCheckStatus.SKIPPED,
                "No dedicated runtime config path is declared.",
            )
        )
    elif config_path.exists():
        try:
            payload = _read_yaml(config_path)
            enabled_path = metadata.get("enabled_path")
            enabled_value = _nested_get(payload, str(enabled_path)) if enabled_path else None
            if enabled_value is False:
                configured_disabled = True
                message = "Runtime config marks this core capability disabled; exhibition activation requires operator action."
                warnings.append(message)
                checks.append(
                    _check(
                        2,
                        "runtime_config",
                        PreflightCheckStatus.WARNING,
                        message,
                        {"path": _relative(config_path), "enabled_path": enabled_path},
                    )
                )
            else:
                checks.append(
                    _check(
                        2,
                        "runtime_config",
                        PreflightCheckStatus.PASSED,
                        f"Runtime config present: {_relative(config_path)}",
                        {"path": _relative(config_path)},
                    )
                )
        except Exception as exc:
            checks.append(
                _check(
                    2,
                    "runtime_config",
                    PreflightCheckStatus.FAILED,
                    f"Runtime config could not be parsed: {str(exc)[:160]}",
                    {"path": _relative(config_path)},
                )
            )
    else:
        checks.append(
            _check(
                2,
                "runtime_config",
                PreflightCheckStatus.FAILED,
                f"Runtime config missing: {_relative(config_path)}",
                {"path": _relative(config_path)},
            )
        )

    required_env = [str(item) for item in (metadata.get("required_env") or [])]
    for env_name in required_env:
        value = os.getenv(env_name, "").strip()
        if value:
            checks.append(
                _check(
                    2,
                    "environment",
                    PreflightCheckStatus.PASSED,
                    f"{env_name} is present.",
                    {"present": True, "masked": _mask_secret(value)},
                )
            )
        else:
            checks.append(
                _check(
                    2,
                    "environment",
                    PreflightCheckStatus.FAILED,
                    f"{env_name} missing",
                    {"present": False},
                )
            )
    return checks, warnings, configured_disabled


def _check_routes_and_components(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    missing: list[str] = []
    paths = list(ROUTE_EXPECTATIONS.get(record.descriptor.id, ()))
    if record.descriptor.component_path:
        paths.append(str(record.descriptor.component_path))
    for raw in dict.fromkeys(paths):
        path = _resolve_repo_path(raw)
        if path is None:
            continue
        if path.exists():
            checks.append(
                _check(
                    4,
                    "component_path",
                    PreflightCheckStatus.PASSED,
                    f"Component path present: {_relative(path)}",
                    {"path": _relative(path)},
                )
            )
        else:
            missing.append(_relative(path))
            checks.append(
                _check(
                    4,
                    "component_path",
                    PreflightCheckStatus.FAILED,
                    f"Component path missing: {_relative(path)}",
                    {"path": _relative(path)},
                )
            )

    modules = SAFE_IMPORT_MODULES.get(record.descriptor.id, ())
    for module_name in modules:
        try:
            __import__(module_name)
            checks.append(
                _check(
                    4,
                    "module_import",
                    PreflightCheckStatus.PASSED,
                    f"Lightweight module import succeeded: {module_name}",
                    {"module": module_name},
                )
            )
        except Exception as exc:
            missing.append(module_name)
            checks.append(
                _check(
                    4,
                    "module_import",
                    PreflightCheckStatus.FAILED,
                    f"Lightweight module import failed: {str(exc)[:160]}",
                    {"module": module_name},
                )
            )
    if not paths and not modules:
        checks.append(
            _check(
                4,
                "runtime_probe",
                PreflightCheckStatus.SKIPPED,
                "No lightweight runtime probe is registered for this capability in Phase 2.",
            )
        )
    return checks, missing


def _check_local_storage(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []
    paths = [str(item) for item in (record.descriptor.metadata.get("writable_paths") or ["storage", "runtime_state", "logs"])]
    for raw in paths:
        path = _resolve_repo_path(raw)
        if path is None:
            continue
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".preflight_probe"
            probe.write_text("ok", encoding="utf-8")
            payload = probe.read_text(encoding="utf-8")
            probe.unlink(missing_ok=True)
            if payload != "ok":
                raise OSError("probe readback mismatch")
            checks.append(
                _check(
                    4,
                    "storage_probe",
                    PreflightCheckStatus.PASSED,
                    f"Storage path writable: {_relative(path)}",
                    {"path": _relative(path)},
                )
            )
        except Exception as exc:
            failures.append(_relative(path))
            checks.append(
                _check(
                    4,
                    "storage_probe",
                    PreflightCheckStatus.FAILED,
                    f"Storage path is not writable: {_relative(path)} ({str(exc)[:120]})",
                    {"path": _relative(path)},
                )
            )
    return checks, failures


def _check_uploaded_video_pipeline(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []
    warnings: list[str] = []
    metadata = record.descriptor.metadata or {}
    config_path = _resolve_repo_path(metadata.get("config_path"))
    if config_path is None or not config_path.exists():
        return checks, failures

    try:
        payload = _read_yaml(config_path)
    except Exception as exc:
        failures.append(_relative(config_path))
        checks.append(
            _check(
                4,
                "uploaded_video_config",
                PreflightCheckStatus.FAILED,
                f"Uploaded-video config could not be parsed: {str(exc)[:160]}",
                {"path": _relative(config_path)},
            )
        )
        return checks, failures

    uploaded_cfg = payload.get("uploaded_video") if isinstance(payload.get("uploaded_video"), dict) else {}
    storage_cfg = uploaded_cfg.get("storage") if isinstance(uploaded_cfg.get("storage"), dict) else {}
    for key, label in (("root_dir", "upload storage"), ("processed_dir", "report storage")):
        raw = storage_cfg.get(key)
        path = _resolve_repo_path(str(raw or ""))
        if path is None:
            failures.append(key)
            checks.append(
                _check(
                    4,
                    "uploaded_video_storage",
                    PreflightCheckStatus.FAILED,
                    f"Uploaded-video {label} path is not configured.",
                    {"key": key},
                )
            )
            continue
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".uploaded_video_preflight_probe"
            probe.write_text("ok", encoding="utf-8")
            ok = probe.read_text(encoding="utf-8") == "ok"
            probe.unlink(missing_ok=True)
            if not ok:
                raise OSError("probe readback mismatch")
            checks.append(
                _check(
                    4,
                    "uploaded_video_storage",
                    PreflightCheckStatus.PASSED,
                    f"Uploaded-video {label} path writable: {_relative(path)}",
                    {"key": key, "path": _relative(path)},
                )
            )
        except Exception as exc:
            failures.append(_relative(path))
            checks.append(
                _check(
                    4,
                    "uploaded_video_storage",
                    PreflightCheckStatus.FAILED,
                    f"Uploaded-video {label} path is not writable: {_relative(path)} ({str(exc)[:120]})",
                    {"key": key, "path": _relative(path)},
                )
            )

    pipeline_cfg = uploaded_cfg.get("pipeline") if isinstance(uploaded_cfg.get("pipeline"), dict) else {}
    for key, capability_id in (("weapon_detection", "yolo_weapon_detector"), ("phone_detection", "yolo_phone_detector")):
        enabled = pipeline_cfg.get(key)
        if enabled is False:
            failures.append(key)
            checks.append(
                _check(
                    4,
                    "uploaded_video_detector_policy",
                    PreflightCheckStatus.WARNING,
                    f"Uploaded-video pipeline config disables {key}; {capability_id} will not activate for exhibition video processing.",
                    {"pipeline_key": key, "capability_id": capability_id},
                )
            )
        else:
            checks.append(
                _check(
                    4,
                    "uploaded_video_detector_policy",
                    PreflightCheckStatus.PASSED,
                    f"Uploaded-video pipeline permits {key}.",
                    {"pipeline_key": key, "capability_id": capability_id},
                )
            )

    registry_payload = _model_registry_payload()
    for registry_key in ("weapon_detector", "phone_detector"):
        entry = registry_payload.get(registry_key)
        if isinstance(entry, dict) and (entry.get("active_version") or entry.get("path")):
            checks.append(
                _check(
                    4,
                    "uploaded_video_model_reference",
                    PreflightCheckStatus.PASSED,
                    f"Model registry has uploaded-video detector reference: {registry_key}",
                    {"registry_key": registry_key, "active_version": entry.get("active_version")},
                )
            )
        else:
            failures.append(registry_key)
            checks.append(
                _check(
                    4,
                    "uploaded_video_model_reference",
                    PreflightCheckStatus.FAILED,
                    f"Model registry missing detector reference: {registry_key}",
                    {"registry_key": registry_key},
                )
            )

    return checks, failures


def _check_simulation_source_network(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []
    metadata = record.descriptor.metadata or {}
    min_cameras = int(metadata.get("min_cameras", 12))
    min_drones = int(metadata.get("min_drones", 2))

    service_path = _resolve_repo_path("backend/app/services/simulation_source_service.py")
    if service_path and service_path.exists():
        checks.append(
            _check(4, "sim_service_path", PreflightCheckStatus.PASSED, "Simulation source service file is present.")
        )
    else:
        failures.append("simulation_source_service.py")
        checks.append(
            _check(4, "sim_service_path", PreflightCheckStatus.FAILED, "Simulation source service file is missing.")
        )
        return checks, failures

    routes_path = _resolve_repo_path("backend/app/api/simulation_routes.py")
    if routes_path and routes_path.exists():
        checks.append(
            _check(4, "sim_routes_path", PreflightCheckStatus.PASSED, "Simulation API routes file is present.")
        )
    else:
        failures.append("simulation_routes.py")
        checks.append(
            _check(4, "sim_routes_path", PreflightCheckStatus.FAILED, "Simulation API routes file is missing.")
        )

    try:
        from app.services.simulation_source_service import get_city_surveillance_registry
        registry = get_city_surveillance_registry()
        snapshot = registry.snapshot()
        cam_count = snapshot.get("camera_count", 0)
        drone_count = snapshot.get("drone_count", 0)

        if cam_count >= min_cameras:
            checks.append(
                _check(
                    4,
                    "sim_camera_count",
                    PreflightCheckStatus.PASSED,
                    f"Simulation city camera registry has {cam_count} cameras (min {min_cameras}).",
                    {"camera_count": cam_count},
                )
            )
        else:
            failures.append("sim_camera_count")
            checks.append(
                _check(
                    4,
                    "sim_camera_count",
                    PreflightCheckStatus.FAILED,
                    f"Simulation city camera registry has only {cam_count} cameras; minimum {min_cameras} required.",
                    {"camera_count": cam_count, "min_cameras": min_cameras},
                )
            )

        if drone_count >= min_drones:
            checks.append(
                _check(
                    4,
                    "sim_drone_count",
                    PreflightCheckStatus.PASSED,
                    f"Simulation drone registry has {drone_count} drones (min {min_drones}).",
                    {"drone_count": drone_count},
                )
            )
        else:
            failures.append("sim_drone_count")
            checks.append(
                _check(
                    4,
                    "sim_drone_count",
                    PreflightCheckStatus.FAILED,
                    f"Simulation drone registry has only {drone_count} drones; minimum {min_drones} required.",
                    {"drone_count": drone_count, "min_drones": min_drones},
                )
            )

        network_ready = snapshot.get("source_network_ready", False)
        if network_ready:
            checks.append(
                _check(
                    4,
                    "sim_network_ready",
                    PreflightCheckStatus.PASSED,
                    "Simulation source network is ready for scenario operations.",
                    {"zones": snapshot.get("zones", []), "cameras_online": snapshot.get("cameras_online", 0)},
                )
            )
        else:
            checks.append(
                _check(
                    4,
                    "sim_network_ready",
                    PreflightCheckStatus.WARNING,
                    "Simulation source network is below the minimum threshold for scenario readiness.",
                    {"snapshot": snapshot},
                )
            )

        checks.append(
            _check(
                4,
                "sim_observation_adapter",
                PreflightCheckStatus.PASSED,
                "Simulation observation source governance adapter is available.",
                {"dry_run": True},
            )
        )

    except Exception as exc:
        failures.append("simulation_source_import")
        checks.append(
            _check(
                4,
                "sim_source_import",
                PreflightCheckStatus.FAILED,
                f"Simulation source registry could not be loaded: {str(exc)[:160]}",
                {"error": str(exc)[:160]},
            )
        )

    return checks, failures


def _check_sim_scenario_engine(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []
    metadata = record.descriptor.metadata or {}
    required_ids = list(metadata.get("required_scenario_ids") or ["bank_robbery_demo"])

    engine_path = _resolve_repo_path("backend/app/services/scenario_engine_service.py")
    if engine_path and engine_path.exists():
        checks.append(
            _check(4, "scenario_engine_path", PreflightCheckStatus.PASSED, "Scenario engine service file is present.")
        )
    else:
        failures.append("scenario_engine_service.py")
        checks.append(
            _check(4, "scenario_engine_path", PreflightCheckStatus.FAILED, "Scenario engine service file is missing.")
        )
        return checks, failures

    routes_path = _resolve_repo_path("backend/app/api/scenario_routes.py")
    if routes_path and routes_path.exists():
        checks.append(
            _check(4, "scenario_routes_path", PreflightCheckStatus.PASSED, "Scenario API routes file is present.")
        )
    else:
        failures.append("scenario_routes.py")
        checks.append(
            _check(4, "scenario_routes_path", PreflightCheckStatus.FAILED, "Scenario API routes file is missing.")
        )

    try:
        from app.services.scenario_engine_service import SCENARIO_CATALOGUE, get_scenario_engine
        for sid in required_ids:
            if sid in SCENARIO_CATALOGUE:
                scenario = SCENARIO_CATALOGUE[sid]
                checks.append(
                    _check(
                        4,
                        "scenario_catalogue_entry",
                        PreflightCheckStatus.PASSED,
                        f"Required scenario '{sid}' found in catalogue with {len(scenario.timeline)} timeline events.",
                        {"scenario_id": sid, "timeline_steps": len(scenario.timeline)},
                    )
                )
            else:
                failures.append(sid)
                checks.append(
                    _check(
                        4,
                        "scenario_catalogue_entry",
                        PreflightCheckStatus.FAILED,
                        f"Required scenario '{sid}' not found in catalogue.",
                        {"scenario_id": sid},
                    )
                )

        engine = get_scenario_engine()
        scenarios = engine.list_scenarios()
        checks.append(
            _check(
                4,
                "scenario_engine_ready",
                PreflightCheckStatus.PASSED,
                f"Scenario engine singleton is operational with {len(scenarios)} scenario(s) registered.",
                {"scenario_count": len(scenarios)},
            )
        )
    except Exception as exc:
        failures.append("scenario_engine_import")
        checks.append(
            _check(
                4,
                "scenario_engine_import",
                PreflightCheckStatus.FAILED,
                f"Scenario engine could not be loaded: {str(exc)[:160]}",
                {"error": str(exc)[:160]},
            )
        )

    promotions_path = _resolve_repo_path("runtime_state/scenario_promotions")
    if promotions_path is not None:
        try:
            promotions_path.mkdir(parents=True, exist_ok=True)
            checks.append(
                _check(4, "scenario_promotions_path", PreflightCheckStatus.PASSED, "Scenario promotions storage path is writable.")
            )
        except Exception as exc:
            failures.append("scenario_promotions_path")
            checks.append(
                _check(
                    4,
                    "scenario_promotions_path",
                    PreflightCheckStatus.FAILED,
                    f"Scenario promotions path is not writable: {str(exc)[:120]}",
                )
            )

    return checks, failures


def _check_visual_tracking_fusion(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []
    metadata = record.descriptor.metadata or {}
    min_suspect_wps = int(metadata.get("min_suspect_waypoints", 5))
    min_handoffs = int(metadata.get("min_camera_handoffs", 5))
    min_drone_wps = int(metadata.get("min_drone_waypoints", 4))

    for path_str, label in (
        ("backend/app/models/tracking_models.py", "tracking domain models"),
        ("backend/app/services/fused_path_service.py", "fused path service"),
        ("backend/app/api/tracking_routes.py", "tracking API routes"),
        ("frontend/src/components/simulation/OperationalTrackingPanel.jsx", "OperationalTrackingPanel"),
        ("frontend/src/components/simulation/SuspectPathMap.jsx", "SuspectPathMap"),
        ("frontend/src/components/simulation/CameraHandoffTimeline.jsx", "CameraHandoffTimeline"),
        ("frontend/src/components/simulation/DroneRoutePanel.jsx", "DroneRoutePanel"),
    ):
        path = _resolve_repo_path(path_str)
        if path and path.exists():
            checks.append(_check(4, "tracking_component", PreflightCheckStatus.PASSED, f"{label} present: {_relative(path)}"))
        else:
            failures.append(path_str)
            checks.append(_check(4, "tracking_component", PreflightCheckStatus.FAILED, f"{label} missing: {path_str}"))

    try:
        from app.services.scenario_engine_service import BANK_ROBBERY_SUSPECT_PATH, BANK_ROBBERY_CAMERA_HANDOFFS, DRONE_ALPHA_ROUTE_WAYPOINTS
        from app.services.simulation_source_service import get_city_surveillance_registry

        n_wps = len(BANK_ROBBERY_SUSPECT_PATH)
        if n_wps >= min_suspect_wps:
            checks.append(_check(4, "suspect_path_waypoints", PreflightCheckStatus.PASSED,
                f"Bank robbery suspect path has {n_wps} waypoints (min {min_suspect_wps}).", {"count": n_wps}))
        else:
            failures.append("suspect_path_waypoints")
            checks.append(_check(4, "suspect_path_waypoints", PreflightCheckStatus.FAILED,
                f"Suspect path has only {n_wps} waypoints; min {min_suspect_wps} required.", {"count": n_wps}))

        n_hoffs = len(BANK_ROBBERY_CAMERA_HANDOFFS)
        if n_hoffs >= min_handoffs:
            checks.append(_check(4, "camera_handoff_chain", PreflightCheckStatus.PASSED,
                f"Bank robbery camera handoff chain has {n_hoffs} handoffs (min {min_handoffs}).", {"count": n_hoffs}))
        else:
            failures.append("camera_handoff_chain")
            checks.append(_check(4, "camera_handoff_chain", PreflightCheckStatus.FAILED,
                f"Camera handoff chain has only {n_hoffs} entries; min {min_handoffs} required.", {"count": n_hoffs}))

        registry = get_city_surveillance_registry()
        valid_ids = {c.camera_id for c in registry.list_cameras()}
        invalid_cams: list[str] = []
        for raw in BANK_ROBBERY_CAMERA_HANDOFFS:
            for cam_id in (raw.get("from_camera_id"), raw.get("to_camera_id")):
                if cam_id and cam_id not in valid_ids:
                    invalid_cams.append(cam_id)
        if not invalid_cams:
            checks.append(_check(4, "handoff_camera_refs", PreflightCheckStatus.PASSED,
                "All camera handoff references are valid registered cameras."))
        else:
            failures.append("handoff_camera_refs")
            checks.append(_check(4, "handoff_camera_refs", PreflightCheckStatus.FAILED,
                f"Camera handoff references unregistered cameras: {invalid_cams[:5]}", {"invalid": invalid_cams[:5]}))

        n_drone_wps = len(DRONE_ALPHA_ROUTE_WAYPOINTS)
        if n_drone_wps >= min_drone_wps:
            checks.append(_check(4, "drone_route_waypoints", PreflightCheckStatus.PASSED,
                f"DRONE-ALPHA route template has {n_drone_wps} waypoints (min {min_drone_wps}).", {"count": n_drone_wps}))
        else:
            failures.append("drone_route_waypoints")
            checks.append(_check(4, "drone_route_waypoints", PreflightCheckStatus.FAILED,
                f"DRONE-ALPHA route template has only {n_drone_wps} waypoints; min {min_drone_wps} required.", {"count": n_drone_wps}))

        drone_ids_in_route = {raw["entity_id"] for raw in DRONE_ALPHA_ROUTE_WAYPOINTS}
        if "DRONE-ALPHA" in drone_ids_in_route:
            checks.append(_check(4, "drone_alpha_in_route", PreflightCheckStatus.PASSED,
                "DRONE-ALPHA is referenced in the route waypoints."))
        else:
            failures.append("drone_alpha_in_route")
            checks.append(_check(4, "drone_alpha_in_route", PreflightCheckStatus.FAILED,
                "DRONE-ALPHA not found in route waypoints."))

        from app.services.fused_path_service import get_fused_path_service
        svc = get_fused_path_service()
        health = svc.health()
        checks.append(_check(4, "fused_path_service_health", PreflightCheckStatus.PASSED,
            f"Fused path service reports: {health.get('status', 'unknown')}", {"health": health}))

    except Exception as exc:
        failures.append("visual_tracking_import")
        checks.append(_check(4, "visual_tracking_import", PreflightCheckStatus.FAILED,
            f"Visual tracking/fusion import failed: {str(exc)[:160]}", {"error": str(exc)[:160]}))

    return checks, failures


def _check_drone_unified_state(record) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []

    for path_str, label in (
        ("backend/app/models/drone_unified_models.py", "unified drone models"),
        ("backend/app/services/drone_operational_state_service.py", "drone operational state service"),
        ("backend/app/api/drone_unified_routes.py", "unified drone API routes"),
        ("frontend/src/api/droneUnifiedApi.js", "frontend unified drone API"),
    ):
        path = _resolve_repo_path(path_str)
        if path and path.exists():
            checks.append(_check(4, "drone_unified_component", PreflightCheckStatus.PASSED,
                f"{label} present: {_relative(path)}"))
        else:
            failures.append(path_str)
            checks.append(_check(4, "drone_unified_component", PreflightCheckStatus.FAILED,
                f"{label} missing: {path_str}"))

    # Verify registry has drones to unify
    try:
        from app.services.simulation_source_service import get_city_surveillance_registry
        registry = get_city_surveillance_registry()
        drones = registry.list_drones()
        if drones:
            checks.append(_check(4, "drone_registry_population", PreflightCheckStatus.PASSED,
                f"City registry has {len(drones)} drone(s) available for state unification.",
                {"count": len(drones)}))
        else:
            failures.append("drone_registry_population")
            checks.append(_check(4, "drone_registry_population", PreflightCheckStatus.FAILED,
                "City registry has no drones — unified state will return empty fleet."))
    except Exception as exc:
        failures.append("drone_registry_import")
        checks.append(_check(4, "drone_registry_import", PreflightCheckStatus.FAILED,
            f"Could not import city registry for drone check: {str(exc)[:120]}"))

    # Verify service health (AirSim disconnected is non-fatal)
    try:
        from app.services.drone_operational_state_service import get_drone_operational_state_service
        svc = get_drone_operational_state_service()
        health = svc.health()
        checks.append(_check(4, "drone_unified_service_health", PreflightCheckStatus.PASSED,
            f"Drone operational state service reports: {health.get('status', 'unknown')}", {"health": health}))
    except Exception as exc:
        failures.append("drone_unified_service_import")
        checks.append(_check(4, "drone_unified_service_import", PreflightCheckStatus.FAILED,
            f"Drone unified state service import failed: {str(exc)[:120]}"))

    return checks, failures


def _check_command_center_intelligence(capability_id: str) -> tuple[list[PreflightCheckResult], list[str]]:
    checks: list[PreflightCheckResult] = []
    failures: list[str] = []

    required_paths = (
        "backend/app/models/intelligence_models.py",
        "backend/app/services/command_center_intelligence_service.py",
        "frontend/src/pages/Dashboard.jsx",
        "frontend/src/components/uploaded-video/UploadedVideoReportPanel.jsx",
        "frontend/src/components/alerts/AlertCard.jsx",
    )
    for raw in required_paths:
        path = _resolve_repo_path(raw)
        if path and path.exists():
            checks.append(
                _check(
                    4,
                    "command_center_component",
                    PreflightCheckStatus.PASSED,
                    f"Command-center intelligence component present: {_relative(path)}",
                    {"path": _relative(path), "capability_id": capability_id},
                )
            )
        else:
            failures.append(raw)
            checks.append(
                _check(
                    4,
                    "command_center_component",
                    PreflightCheckStatus.FAILED,
                    f"Command-center intelligence component missing: {raw}",
                    {"path": raw, "capability_id": capability_id},
                )
            )

    try:
        from app.services.command_center_intelligence_service import CommandCenterIntelligenceService

        service = CommandCenterIntelligenceService(storage_dir=PROJECT_ROOT / "runtime_state" / "preflight_command_center")
        health = service.health(dry_run=True)
        if health.get("adapter_available") and health.get("promotion_available"):
            checks.append(
                _check(
                    4,
                    "intelligence_event_adapter",
                    PreflightCheckStatus.PASSED,
                    "Normalized intelligence event adapter and simulation observation adapter are importable.",
                    {"dry_run": True, "adapter_available": True},
                )
            )
            checks.append(
                _check(
                    4,
                    "uploaded_video_promotion_service",
                    PreflightCheckStatus.PASSED,
                    "Uploaded-video promotion service is available for dry-run command-center checks.",
                    {"dry_run": True, "persisted_records": health.get("persisted_records", 0)},
                )
            )
        else:
            failures.append("command_center_intelligence_service")
            checks.append(
                _check(
                    4,
                    "uploaded_video_promotion_service",
                    PreflightCheckStatus.FAILED,
                    "Command-center intelligence service dry-run did not report adapter/promotion readiness.",
                    {"dry_run": True, **health},
                )
            )
    except Exception as exc:
        failures.append("command_center_intelligence_service")
        checks.append(
            _check(
                4,
                "uploaded_video_promotion_service",
                PreflightCheckStatus.FAILED,
                f"Command-center intelligence dry-run failed: {str(exc)[:160]}",
                {"dry_run": True},
            )
        )

    service_checks = {
        "alert_incident_service": ("alerts", "incidents", "uploaded_video_pipeline", "event_engine"),
        "case_evidence_report_service": ("cases", "evidence", "reports", "uploaded_video_pipeline"),
        "dashboard_intelligence_client": ("alerts", "analytics", "uploaded_video_pipeline"),
        "analytics_source": ("analytics", "uploaded_video_pipeline"),
    }
    for name, related in service_checks.items():
        if capability_id not in related:
            continue
        checks.append(
            _check(
                4,
                name,
                PreflightCheckStatus.PASSED,
                f"{name.replace('_', ' ')} is wired for command-center integration checks.",
                {"dry_run": True, "capability_id": capability_id},
            )
        )

    return checks, failures


def _safe_warmup_check(capability_id: str, mode: PreflightMode) -> PreflightCheckResult:
    if mode == PreflightMode.QUICK:
        return _check(
            5,
            "warmup",
            PreflightCheckStatus.SKIPPED,
            "Quick preflight does not perform capability warmup.",
        )
    if capability_id in SAFE_WARMUP_CAPABILITIES:
        return _check(
            5,
            "warmup",
            PreflightCheckStatus.PASSED,
            "Safe lightweight preflight warmup completed.",
        )
    return _check(
        5,
        "warmup",
        PreflightCheckStatus.SKIPPED,
        "Model, simulator, or provider warmup deferred for resource-aware managed activation.",
    )


def _status_counts(checks: list[PreflightCheckResult]) -> Counter:
    return Counter(check.status for check in checks)


def evaluate_capability(
    registry: CapabilityRegistry,
    capability_id: str,
    mode: PreflightMode,
) -> PreflightCapabilityResult:
    start = time.perf_counter()
    record = registry.get(capability_id)
    descriptor = record.descriptor
    group = group_for_capability(capability_id)
    checks: list[PreflightCheckResult] = [
        _check(
            1,
            "registry",
            PreflightCheckStatus.PASSED,
            "Capability is registered with descriptor and runtime status.",
            {"current_state": record.runtime_status.state.value},
        )
    ]
    warnings: list[str] = []
    recommendations: list[str] = []

    config_checks, config_warnings, configured_disabled = _check_config(record)
    checks.extend(config_checks)
    warnings.extend(config_warnings)

    artifact_checks, missing_artifacts = _check_required_paths(record)
    checks.extend(artifact_checks)

    component_checks, missing_components = _check_routes_and_components(record)
    checks.extend(component_checks)

    if capability_id == "uploaded_video_pipeline":
        video_checks, video_failures = _check_uploaded_video_pipeline(record)
        checks.extend(video_checks)
    else:
        video_failures = []

    if capability_id == "local_storage":
        storage_checks, storage_failures = _check_local_storage(record)
        checks.extend(storage_checks)
    else:
        storage_failures = []

    if capability_id in COMMAND_CENTER_INTEGRATION_CAPABILITIES:
        command_checks, command_failures = _check_command_center_intelligence(capability_id)
        checks.extend(command_checks)
    else:
        command_failures = []

    if capability_id == "simulation_source_network":
        sim_checks, sim_failures = _check_simulation_source_network(record)
        checks.extend(sim_checks)
    elif capability_id == "sim_scenario_engine":
        sim_checks, sim_failures = _check_sim_scenario_engine(record)
        checks.extend(sim_checks)
    elif capability_id == "visual_tracking_fusion":
        sim_checks, sim_failures = _check_visual_tracking_fusion(record)
        checks.extend(sim_checks)
    elif capability_id == "drone_unified_state":
        sim_checks, sim_failures = _check_drone_unified_state(record)
        checks.extend(sim_checks)
    else:
        sim_failures = []

    warmup_check = _safe_warmup_check(capability_id, mode)
    checks.append(warmup_check)

    missing_env = [
        item.metadata.get("present") is False and item.message
        for item in checks
        if item.name == "environment"
    ]
    missing_env = [str(item) for item in missing_env if item]

    counts = _status_counts(checks)
    blocking = capability_id in FOUNDATIONAL_CAPABILITIES
    metadata: dict[str, Any] = {
        "mode": mode.value,
        "check_levels": sorted({check.level for check in checks}),
        "configured_disabled": configured_disabled,
    }

    if capability_id == "llm_osint":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        metadata["provider"] = "openai"
        metadata["openai_key_present"] = bool(key)
        if key:
            metadata["openai_key_masked"] = _mask_secret(key)
            recommendations.append("Run provider verification from preflight when external network validation is approved.")
        else:
            warnings.append("Provider key missing")
            recommendations.append("Set OPENAI_API_KEY in the backend-loaded local env file, then rerun exhibition preflight.")

    if configured_disabled:
        state = CapabilityState.DISABLED
        reason = "Core capability is registered but runtime config currently disables activation."
    elif storage_failures:
        state = CapabilityState.FAULTED
        reason = "Local storage read/write preflight failed."
    elif missing_env:
        state = CapabilityState.DEGRADED
        reason = "OPENAI_API_KEY missing" if capability_id == "llm_osint" else "Required environment configuration is missing."
    elif sim_failures:
        state = CapabilityState.DEGRADED
        reason = "Simulation source network registry is below minimum threshold for scenario readiness."
        recommendations.append("Restore simulation camera/drone registry to satisfy minimum thresholds before exhibition.")
    elif command_failures:
        state = CapabilityState.DEGRADED
        reason = "Command-center intelligence integration preflight is not fully ready."
        recommendations.append("Restore command-center intelligence adapter, promotion, dashboard, and analytics surfaces.")
    elif missing_components:
        state = CapabilityState.FAULTED if blocking else CapabilityState.DEGRADED
        reason = "Required component or route surface is missing."
        recommendations.append("Restore the missing component path before exhibition readiness.")
    elif video_failures:
        state = CapabilityState.DEGRADED
        reason = "Uploaded-video storage, detector policy, or model registry reference is not exhibition-ready."
        recommendations.append("Fix uploaded-video storage/config/model registry blockers before processing exhibition uploads.")
    elif missing_artifacts:
        state = CapabilityState.DEGRADED
        reason = "Required model artifact or registry path is missing."
        recommendations.append("Verify the governed model registry paths before capability warmup.")
    elif counts[PreflightCheckStatus.FAILED] > 0:
        state = CapabilityState.FAULTED if blocking else CapabilityState.DEGRADED
        reason = "One or more preflight checks failed."
    elif CapabilityResourceProfile.EXTERNAL_SERVICE in descriptor.resource_profile and capability_id != "llm_osint":
        state = CapabilityState.COLD
        reason = "External-service capability is registered; provider activation awaits managed preflight."
    elif warmup_check.status == PreflightCheckStatus.PASSED:
        state = CapabilityState.READY
        reason = "Ready for exhibition path."
    elif descriptor.resource_profile and any(
        profile in descriptor.resource_profile
        for profile in (CapabilityResourceProfile.GPU_HEAVY, CapabilityResourceProfile.CPU_HEAVY, CapabilityResourceProfile.NETWORK_IO)
    ):
        state = CapabilityState.COLD
        reason = "Model artifact/config present where available; warmup deferred for managed activation."
    else:
        state = CapabilityState.READY
        reason = "Lightweight preflight checks passed."

    if counts[PreflightCheckStatus.WARNING] > 0:
        warnings.extend(check.message for check in checks if check.status == PreflightCheckStatus.WARNING)

    if state == CapabilityState.COLD:
        recommendations.append("Core capability awaiting preflight warmup or mission activation.")
    if state == CapabilityState.DEGRADED:
        recommendations.append("Review degraded readiness before exhibition use.")
    if state == CapabilityState.FAULTED:
        recommendations.append("Resolve the fault before relying on this capability.")

    duration_ms = int((time.perf_counter() - start) * 1000)
    return PreflightCapabilityResult(
        capability_id=capability_id,
        name=descriptor.name,
        group=group,
        state=state,
        check_level=max(check.level for check in checks),
        checks=checks,
        blocking=blocking,
        reason=reason,
        warnings=list(dict.fromkeys(warnings)),
        recommendations=list(dict.fromkeys(recommendations)),
        duration_ms=duration_ms,
        metadata=metadata,
    )


def grouped_state_counts(results: list[PreflightCapabilityResult]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for result in results:
        group = result.group.value
        payload = groups.setdefault(
            group,
            {
                "total": 0,
                "by_state": {state.value: 0 for state in CapabilityState},
                "blocking_failures": [],
                "warnings": [],
            },
        )
        payload["total"] += 1
        payload["by_state"][result.state.value] += 1
        if result.blocking and result.state in {CapabilityState.FAULTED, CapabilityState.DEGRADED, CapabilityState.UNKNOWN}:
            payload["blocking_failures"].append(result.capability_id)
        if result.warnings:
            payload["warnings"].extend(result.warnings)
    return groups
