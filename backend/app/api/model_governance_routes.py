from __future__ import annotations

import os
from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.security_dependencies import require_permission
from app.models.security_models import AuditAction, UserAccount
from app.repositories.model_registry_repository import (
    FileModelRegistryRepository,
    get_model_registry_repository,
    reset_model_registry_repository,
)
from app.services.model_drift_service import summarize_drift_for_model
from app.services.model_governance_service import (
    evaluate_promotion,
    evaluate_runtime_model_governance,
    get_active_models_view,
    get_entry_by_model_id,
    get_limitations_view,
    list_registry_for_api,
    load_model_governance_config,
    rollback_registry_version,
)

router = APIRouter(prefix="/api/model-governance", tags=["model-governance"])


@router.get("/registry")
async def list_registry_entries(_user: UserAccount = Depends(require_permission("model:read"))):
    return {"entries": list_registry_for_api()}


@router.get("/registry/{model_id}")
async def get_registry_entry(model_id: str, _user: UserAccount = Depends(require_permission("model:read"))):
    row = get_entry_by_model_id(model_id)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown model_id")
    return row


@router.get("/active")
async def active_models(_user: UserAccount = Depends(require_permission("model:read"))):
    return {"models": get_active_models_view()}


@router.get("/limitations")
async def limitations(_user: UserAccount = Depends(require_permission("model:read"))):
    return {"limitations": get_limitations_view()}


@router.get("/promotion-policy")
async def promotion_policy(_user: UserAccount = Depends(require_permission("model:read"))):
    cfg = dict((load_model_governance_config().get("model_governance") or {}).get("promotion_policy") or {})
    return {"promotion_policy": cfg}


class ValidateBody(BaseModel):
    profile: str | None = Field(default=None, description="development|production override")


@router.post("/validate")
async def validate_models(
    request: Request,
    body: ValidateBody | None = None,
    current_user: UserAccount = Depends(require_permission("model:read")),
):
    profile = (body.profile if body and body.profile else None) or (
        "production" if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} else "development"
    )
    report = evaluate_runtime_model_governance(profile=profile)
    try:
        from app.services.audit_log_service import get_audit_log_service

        get_audit_log_service().record(
            AuditAction.MODEL_GOVERNANCE_VALIDATE,
            user=current_user,
            resource_type="model_governance",
            resource_id="validate",
            success=True,
            detail=f"profile={profile}",
            request=request,
            metadata={"status": report.get("status")},
        )
    except Exception:
        pass
    return report


class RollbackBody(BaseModel):
    model_key: str = Field(..., min_length=1)
    target_version: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=4)


@router.post("/rollback")
async def rollback_model(
    body: RollbackBody,
    request: Request,
    current_user: UserAccount = Depends(require_permission("model:rollback")),
):
    try:
        result = rollback_registry_version(
            model_key=body.model_key,
            target_version=body.target_version,
            reason=body.reason,
            user=current_user,
            request=request,
        )
        return {"status": "ok", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PromoteBody(BaseModel):
    model_key: str
    target_version: str
    exception_approved: bool = False


@router.post("/promote")
async def promote_model(
    body: PromoteBody,
    request: Request,
    current_user: UserAccount = Depends(require_permission("model:approve")),
):
    del request
    res = evaluate_promotion(
        model_key=body.model_key,
        target_version=body.target_version,
        exception_approved=body.exception_approved,
    )
    if not res.allowed:
        try:
            from app.services.audit_log_service import get_audit_log_service

            get_audit_log_service().record(
                AuditAction.MODEL_GOVERNANCE_PROMOTION_DENIED,
                user=current_user,
                resource_type="model_registry",
                resource_id=body.model_key,
                success=False,
                detail=";".join(res.reasons),
                metadata={"target_version": body.target_version},
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail={"reasons": res.reasons})

    repo = get_model_registry_repository()
    if not isinstance(repo, FileModelRegistryRepository) or not repo.allow_writes:
        raise HTTPException(status_code=501, detail="promotion_pointer_updates_require_enable_file_writes")

    snap = deepcopy(repo.read_snapshot())
    block = snap.get(body.model_key)
    if not isinstance(block, dict):
        raise HTTPException(status_code=404, detail="unknown_model_key")
    versions = {k for k, v in block.items() if isinstance(v, dict) and "path" in v}
    if body.target_version not in versions:
        raise HTTPException(status_code=400, detail="target_version_not_in_registry")
    block["active_version"] = body.target_version
    snap[body.model_key] = block
    repo.write_snapshot(snap)
    reset_model_registry_repository()
    try:
        from app.services.audit_log_service import get_audit_log_service

        get_audit_log_service().record(
            AuditAction.MODEL_UPDATED,
            user=current_user,
            resource_type="model_registry",
            resource_id=body.model_key,
            success=True,
            detail=f"active_version->{body.target_version}",
            metadata={"promotion": True, "exception_approved": body.exception_approved},
        )
    except Exception:
        pass
    return {"status": "ok", "model_key": body.model_key, "active_version": body.target_version}


@router.get("/drift/{model_id}")
async def drift_for_model(model_id: str, _user: UserAccount = Depends(require_permission("model:read"))):
    return summarize_drift_for_model(model_id)
