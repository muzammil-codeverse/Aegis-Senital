"""Model governance: registry validation, promotion policy, rollback metadata."""
from __future__ import annotations

import logging
import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dataclasses import dataclass, field

from app.models.security_models import AuditAction, UserAccount
from app.repositories.model_registry_repository import (
    FileModelRegistryRepository,
    ModelRegistryRepository,
    get_model_registry_repository,
    reset_model_registry_repository,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "model_governance.yaml"
IDENTITY_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "identity.yaml"


@dataclass(slots=True)
class PromotionEvaluationResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    exception_required: bool = False


def governance_entry_dict(meta: dict[str, Any], *, model_key: str, version: str, path: str, model_name: str) -> dict[str, Any]:
    """Normalize a registry version payload for API / validation."""
    return {
        "model_key": model_key,
        "version": version,
        "path": path,
        "model_name": model_name,
        **{k: v for k, v in meta.items() if k not in {"model_name", "version", "path"}},
    }


@lru_cache(maxsize=1)
def load_model_governance_config() -> dict[str, Any]:
    if not GOVERNANCE_CONFIG_PATH.exists():
        return {"model_governance": {"enabled": False}}
    data = yaml.safe_load(GOVERNANCE_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {"model_governance": {"enabled": False}}


def reset_model_governance_config_cache() -> None:
    load_model_governance_config.cache_clear()


def _mg() -> dict[str, Any]:
    return dict((load_model_governance_config().get("model_governance") or {}))


def _resolve_registry_entry(snapshot: dict[str, Any], model_key: str, version_selector: str) -> tuple[str | None, dict[str, Any] | None]:
    block = snapshot.get(model_key)
    if not isinstance(block, dict):
        return None, None
    if "path" in block:
        return str(block.get("version") or "current"), block
    active = str(block.get("active_version") or "").strip()
    versions = {k: v for k, v in block.items() if isinstance(v, dict) and "path" in v and k not in {"active_version", "active_rollout"}}
    if version_selector == "latest":
        if active and active in versions:
            return active, versions[active]
        if not versions:
            return None, None
        ordered = sorted(versions.items(), key=lambda kv: (str((kv[1] or {}).get("created_at") or ""), kv[0]))
        return ordered[-1][0], ordered[-1][1]
    sel = version_selector
    if sel in versions:
        return sel, versions[sel]
    return None, None


def _path_exists(rel: str, *, logical_only: bool) -> bool:
    if logical_only:
        return True
    if not rel:
        return False
    p = PROJECT_ROOT / rel
    if not p.exists():
        return False
    if p.is_dir():
        return any(p.rglob("*.onnx")) or any(p.rglob("*.pt")) or any(p.rglob("*.pth")) or any(p.rglob("*.safetensors"))
    return True


def evaluate_runtime_model_governance(*, profile: str) -> dict[str, Any]:
    """Return structured governance gate used by validate_runtime and runtime health."""
    cfg = _mg()
    if not bool(cfg.get("enabled", True)):
        return {
            "status": "disabled",
            "active_models": [],
            "missing_registry_entries": [],
            "missing_metrics": [],
            "missing_limitations": [],
            "production_blockers": [],
            "detail": "model governance disabled in config",
        }

    try:
        repo = get_model_registry_repository()
        snapshot = repo.read_snapshot()
    except Exception as exc:
        return {
            "status": "failed",
            "active_models": [],
            "missing_registry_entries": [f"registry_unreadable:{exc}"],
            "missing_metrics": [],
            "missing_limitations": [],
            "production_blockers": [str(exc)],
            "detail": str(exc),
        }

    bindings = list(cfg.get("runtime_model_bindings") or [])
    missing_reg: list[str] = []
    missing_metrics: list[str] = []
    missing_limits: list[str] = []
    blockers: list[str] = []
    active_models: list[dict[str, Any]] = []

    for binding in bindings:
        gid = str(binding.get("governance_id") or "")
        mkey = str(binding.get("registry_model_key") or "")
        vsel = str(binding.get("version_selector") or "latest")
        optional_path = bool(binding.get("optional_path"))
        logical_only = bool(binding.get("logical_only"))
        ver, meta = _resolve_registry_entry(snapshot, mkey, vsel)
        if not meta:
            missing_reg.append(f"{gid}:{mkey}")
            if profile == "production":
                blockers.append(f"missing_registry:{mkey}")
            continue
        rel_path = str(meta.get("path") or "")
        exists = _path_exists(rel_path, logical_only=logical_only or optional_path)
        if not exists and profile == "production" and not optional_path and not logical_only:
            blockers.append(f"missing_weights:{mkey}:{rel_path}")
        elif not exists and profile == "development" and not optional_path and not logical_only:
            blockers.append(f"warn_missing_weights:{mkey}:{rel_path}")

        status = str(meta.get("status") or "unknown")
        approval = str(meta.get("approval_status") or "")
        lim = meta.get("known_limitations")
        metrics = meta.get("metrics")

        if status == "active" and approval == "deprecated" and not bool((cfg.get("development_overrides") or {}).get("allow_deprecated_active")):
            if profile == "production":
                blockers.append(f"deprecated_active:{mkey}")

        if isinstance(metrics, dict) and len(metrics) == 0 and str(meta.get("approval_status") or "") == "production_pending":
            missing_metrics.append(f"{mkey}/{ver or vsel}")

        if str(status).lower() == "active":
            if not isinstance(lim, list) or len(lim) == 0:
                missing_limits.append(f"{mkey}/{ver or vsel}")

        row = governance_entry_dict(
            dict(meta),
            model_key=mkey,
            version=str(ver or vsel),
            path=rel_path,
            model_name=str(meta.get("model_name") or mkey),
        )
        row["governance_id"] = gid
        row["task_label"] = binding.get("task_label")
        active_models.append(row)

    # Identity / liveness explicit policy
    try:
        id_cfg = yaml.safe_load(IDENTITY_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        ident = id_cfg.get("identity", id_cfg)
        live_on = bool((ident.get("liveness") or {}).get("enabled", False))
        provider = str((ident.get("liveness") or {}).get("provider") or "none").lower()
        if live_on and provider in {"", "none"}:
            msg = "identity_liveness_enabled_without_provider"
            blockers.append(msg if profile == "production" else f"warn:{msg}")
    except Exception as exc:
        blockers.append(f"identity_config_unreadable:{exc}")

    # Anomaly live eval report
    anomaly_pol = dict((cfg.get("promotion_policy") or {}).get("anomaly") or {})
    if bool(anomaly_pol.get("require_live_eval_report")):
        rep = PROJECT_ROOT / str((cfg.get("anomaly_live_eval") or {}).get("report_path") or "storage/anomaly_live_eval/live_eval_summary.json")
        if not rep.exists():
            if profile == "production":
                blockers.append("anomaly_live_eval_report_missing")
            else:
                blockers.append("warn:anomaly_live_eval_report_missing")

    if profile == "production" and missing_limits:
        for m in missing_limits:
            blockers.append(f"missing_limitations:{m}")

    status = "healthy"
    if any(b for b in blockers if not str(b).startswith("warn:")):
        status = "failed" if profile == "production" else "degraded"
    elif blockers:
        status = "degraded"

    return {
        "status": status,
        "active_models": active_models,
        "missing_registry_entries": missing_reg,
        "missing_metrics": missing_metrics,
        "missing_limitations": missing_limits,
        "production_blockers": blockers,
    }


def list_registry_for_api(repo: ModelRegistryRepository | None = None) -> list[dict[str, Any]]:
    r = repo or get_model_registry_repository()
    out: list[dict[str, Any]] = []
    snap = r.read_snapshot()
    for model_key, block in snap.items():
        if not isinstance(block, dict):
            continue
        if "path" in block:
            out.append(governance_entry_dict(dict(block), model_key=model_key, version=str(block.get("version") or "current"), path=str(block.get("path") or ""), model_name=str(block.get("model_name") or model_key)))
            continue
        for ver, meta in block.items():
            if ver in {"active_version", "active_rollout"} or not isinstance(meta, dict) or "path" not in meta:
                continue
            out.append(governance_entry_dict(dict(meta), model_key=model_key, version=str(ver), path=str(meta.get("path") or ""), model_name=str(meta.get("model_name") or model_key)))
    return out


def get_entry_by_model_id(model_id: str, repo: ModelRegistryRepository | None = None) -> dict[str, Any] | None:
    for row in list_registry_for_api(repo):
        if str(row.get("model_id")) == model_id:
            return row
    return None


def get_active_models_view(repo: ModelRegistryRepository | None = None) -> list[dict[str, Any]]:
    rows = list_registry_for_api(repo)
    return [r for r in rows if str(r.get("status") or "").lower() == "active"]


def get_limitations_view(repo: ModelRegistryRepository | None = None) -> list[dict[str, Any]]:
    out = []
    for row in list_registry_for_api(repo):
        out.append(
            {
                "model_id": row.get("model_id"),
                "model_key": row.get("model_key"),
                "version": row.get("version"),
                "known_limitations": row.get("known_limitations") or [],
            }
        )
    return out


def evaluate_promotion(
    *,
    model_key: str,
    target_version: str,
    exception_approved: bool,
) -> PromotionEvaluationResult:
    cfg = _mg()
    policy_root = dict(cfg.get("promotion_policy") or {})
    repo = get_model_registry_repository()
    snap = repo.read_snapshot()
    _ver, meta = _resolve_registry_entry(snap, model_key, target_version)
    if not meta:
        return PromotionEvaluationResult(False, reasons=["unknown_model_or_version"])

    reasons: list[str] = []
    approval_cfg = dict(cfg.get("approval") or {})

    if bool(approval_cfg.get("require_known_limitations", True)):
        lim = meta.get("known_limitations")
        if not isinstance(lim, list) or len(lim) == 0:
            reasons.append("known_limitations_required")

    if bool(approval_cfg.get("require_metrics_for_promotion", True)):
        metrics = meta.get("metrics")
        if not isinstance(metrics, dict) or len(metrics) == 0:
            reasons.append("metrics_required_for_promotion_empty")

    if bool(approval_cfg.get("require_owner", True)) and not str(meta.get("owner") or "").strip():
        reasons.append("owner_required")

    if bool(approval_cfg.get("require_validation_status", True)) and not str(meta.get("validation_status") or "").strip():
        reasons.append("validation_status_required")

    task = str(meta.get("task") or "")
    if task == "weapon_detection":
        wp = dict(policy_root.get("weapon") or {})
        m = dict(meta.get("metrics") or {})
        if m.get("mAP50") is not None and float(m["mAP50"]) < float(wp.get("min_map50", 0)):
            reasons.append("weapon_map50_below_policy")
        if m.get("recall") is not None and float(m["recall"]) < float(wp.get("min_recall", 0)):
            reasons.append("weapon_recall_below_policy")

    allowed = len(reasons) == 0 or exception_approved
    if exception_approved and reasons:
        return PromotionEvaluationResult(True, reasons=reasons + ["exception_approved"], exception_required=True)
    return PromotionEvaluationResult(allowed, reasons=reasons)


def rollback_registry_version(
    *,
    model_key: str,
    target_version: str,
    reason: str,
    user: UserAccount | None,
    request: Any | None,
) -> dict[str, Any]:
    cfg = _mg()
    rb = dict(cfg.get("rollback") or {})
    if not bool(rb.get("enabled", True)):
        raise ValueError("rollback_disabled")
    if bool(rb.get("require_audit_reason", True)) and (not reason or not str(reason).strip()):
        raise ValueError("rollback_reason_required")

    repo = get_model_registry_repository()
    if not isinstance(repo, FileModelRegistryRepository):
        raise ValueError("rollback_requires_file_registry")
    if not repo.allow_writes:
        raise ValueError("registry_file_writes_disabled")

    snap = deepcopy(repo.read_snapshot())
    block = snap.get(model_key)
    if not isinstance(block, dict):
        raise ValueError("unknown_model_key")
    versions = {k: v for k, v in block.items() if isinstance(v, dict) and "path" in v and k not in {"active_version", "active_rollout"}}
    if target_version not in versions:
        raise ValueError("unknown_target_version")

    previous = str(block.get("active_version") or "")
    block["active_version"] = target_version
    snap[model_key] = block

    repo.write_snapshot(snap)
    reset_model_registry_repository()

    try:
        from app.services.audit_log_service import get_audit_log_service

        get_audit_log_service().record(
            AuditAction.MODEL_GOVERNANCE_ROLLBACK,
            user=user,
            resource_type="model_registry",
            resource_id=model_key,
            success=True,
            detail=f"active_version -> {target_version}",
            request=request,
            metadata={"previous_active_version": previous, "reason": reason[:500]},
        )
    except Exception as exc:
        logger.error("audit_failed_after_rollback:%s", exc)

    return {"model_key": model_key, "active_version": target_version, "previous": previous}


def validate_governance_in_process() -> dict[str, Any]:
    """POST /validate body-free orchestration."""
    profile = "production" if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} else "development"
    return evaluate_runtime_model_governance(profile=profile)
