from __future__ import annotations

import json
import os
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.case_models import CaseExport
from app.models.llm_models import LlmGeneratedOutput, LlmSummaryRequest, SourceReference
from app.services.audit_log_service import AuditLogService, get_audit_log_service
from app.services.case_service import CaseService, get_case_service
from app.services.evidence_integrity import safe_evidence_metadata
from app.services.llm_provider import LocalStubProvider, OpenAIResponsesProvider
from inference.config_runtime import load_runtime_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_ENVS = {"prod", "production"}
TEST_ENVS = {"test", "testing"}
LLM_OPERATOR_REVIEW_CAVEAT = (
    "This report is an automated decision-support draft based on available system evidence. "
    "It requires operator review and must not be treated as a final attribution, identity confirmation, or criminality determination."
)
LLM_INSUFFICIENT_EVIDENCE_RESPONSE = "The available case evidence does not contain enough information to answer that."
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
PROHIBITED_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bcriminal confirmed\b", re.IGNORECASE), "possible high-severity event"),
    (re.compile(r"\bsuspect guilty\b", re.IGNORECASE), "operator review required"),
    (re.compile(r"\bidentity confirmed\b", re.IGNORECASE), "possible identity match"),
    (re.compile(r"\bdefinitely armed\b", re.IGNORECASE), "possible weapon-related detection"),
    (re.compile(r"\bconfirmed attacker\b", re.IGNORECASE), "person associated with this event"),
    (re.compile(r"\bterrorist\b", re.IGNORECASE), "person associated with this event"),
    (re.compile(r"\bguilty\b", re.IGNORECASE), "operator review required"),
)

_LLM_SERVICE: "LlmService | None" = None
_LLM_SERVICE_LOCK = threading.Lock()

try:  # pragma: no cover - optional bootstrap behavior
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "backend" / ".env")
except Exception:
    pass


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _environment_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("AEGIS_ENV") or "development").strip().lower()


def _is_production() -> bool:
    return _environment_name() in PRODUCTION_ENVS


def _is_test_environment() -> bool:
    if _is_production():
        return False
    env_name = _environment_name()
    return env_name in TEST_ENVS or bool(os.getenv("PYTEST_CURRENT_TEST"))


@lru_cache(maxsize=1)
def load_llm_config() -> dict[str, Any]:
    payload = load_runtime_config("llm")
    if not isinstance(payload, dict):
        raise ValueError("Invalid llm runtime config")
    return payload


def reset_llm_config() -> None:
    load_llm_config.cache_clear()


class LlmService:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        case_service: CaseService | None = None,
        audit_service: AuditLogService | None = None,
    ) -> None:
        self._raw_config = config or load_llm_config()
        self._config = dict(self._raw_config.get("llm") or {})
        self._case_service = case_service or get_case_service()
        self._audit_service = audit_service or get_audit_log_service()
        self._providers: dict[str, Any] = {}

    def status(self) -> dict[str, Any]:
        providers = dict(self._config.get("providers") or {})
        openai_cfg = dict(providers.get("openai") or {})
        local_stub_cfg = dict(providers.get("local_stub") or {})
        provider_name = str(self._config.get("provider") or self._config.get("default_provider") or "local_stub").lower()
        api_key_env = str(openai_cfg.get("api_key_env") or "OPENAI_API_KEY")
        model_env = str(openai_cfg.get("model_env") or "OPENAI_LLM_MODEL")
        escalation_model_env = str(openai_cfg.get("escalation_model_env") or "OPENAI_LLM_ESCALATION_MODEL")
        final_report_model_env = str(openai_cfg.get("final_report_model_env") or "OPENAI_LLM_FINAL_REPORT_MODEL")
        key_present = bool(os.getenv(api_key_env, "").strip())
        fallback_allowed = bool((self._config.get("development") or {}).get("allow_local_stub_if_openai_key_missing", True))
        enabled = bool(self._config.get("enabled", False))
        using_stub_for_tests = _is_test_environment() and bool(local_stub_cfg.get("enabled", True))
        using_fallback = (
            enabled
            and provider_name == "openai"
            and not key_present
            and fallback_allowed
            and bool(local_stub_cfg.get("enabled", True))
            and not _is_production()
            and not using_stub_for_tests
        )
        active_provider = "local_stub" if using_stub_for_tests or using_fallback else provider_name
        if not enabled:
            state = "disabled"
            detail = "LLM intelligence layer is disabled."
        elif provider_name == "openai" and not bool(openai_cfg.get("enabled", True)):
            state = "error" if _is_production() else "degraded"
            detail = "OpenAI provider is selected but disabled in config."
        elif provider_name == "openai" and not key_present:
            if using_stub_for_tests:
                state = "ok"
                detail = "Tests are pinned to local_stub."
            elif using_fallback:
                state = "degraded"
                detail = "OPENAI_API_KEY is missing; local_stub fallback is active."
            else:
                state = "error" if _is_production() else "degraded"
                detail = f"{api_key_env} is missing."
        else:
            state = "ok"
            detail = f"{active_provider} provider is ready."
        return {
            "enabled": enabled,
            "status": state,
            "detail": detail,
            "mode": str(self._config.get("mode") or "assistive_only"),
            "provider": provider_name,
            "active_provider": active_provider,
            "default_provider": str(self._config.get("default_provider") or provider_name),
            "openai_key_env": api_key_env,
            "openai_key_present": key_present,
            "model_env": model_env,
            "escalation_model_env": escalation_model_env,
            "final_report_model_env": final_report_model_env,
            "dev_fallback_enabled": fallback_allowed,
            "using_fallback": using_fallback or using_stub_for_tests,
            "default_model": self._resolve_openai_model("default"),
            "escalation_model": self._resolve_openai_model("escalation"),
            "final_report_model": self._resolve_openai_model("final_report"),
            "require_explicit_escalation": bool(((openai_cfg.get("cost_control") or {}).get("require_explicit_escalation", True))),
            "max_input_tokens": int(((openai_cfg.get("cost_control") or {}).get("max_input_tokens") or 120000)),
            "max_output_tokens": int(((openai_cfg.get("cost_control") or {}).get("max_output_tokens") or 1800)),
            "production_fail_if_provider_missing": bool(((self._config.get("production") or {}).get("fail_if_enabled_provider_missing", True))),
            "production_fail_if_openai_key_missing": bool(((self._config.get("production") or {}).get("fail_if_openai_key_missing", True))),
        }

    def health(self) -> dict[str, Any]:
        return self.status()

    def verify_provider(
        self,
        model_override: str | None = None,
        *,
        include_escalation: bool = False,
        include_final_report: bool = False,
    ) -> dict[str, Any]:
        status = self.status()
        provider_name = str(status["provider"])
        default_model = str(model_override or status["default_model"])
        if provider_name != "openai":
            return {
                "status": "not_verified",
                "detail": f"Provider '{provider_name}' is configured instead of OpenAI.",
                "provider": provider_name,
                "model": default_model,
                "models_checked": [],
                "response_preview": None,
            }
        if not status["openai_key_present"]:
            return {
                "status": "not_verified",
                "detail": "OpenAI provider not verified because OPENAI_API_KEY is missing.",
                "provider": "openai",
                "model": default_model,
                "models_checked": [],
                "response_preview": None,
            }
        provider = self._get_provider("openai")
        assert isinstance(provider, OpenAIResponsesProvider)
        model_checks: list[dict[str, Any]] = []
        requested_models = [("default", default_model, "low")]
        if include_escalation:
            requested_models.append(("escalation", status["escalation_model"], "medium"))
        if include_final_report:
            requested_models.append(("final_report", status["final_report_model"], "medium"))
        try:
            for model_kind, model_name, effort in requested_models:
                model_checks.append(
                    {
                        "kind": model_kind,
                        **provider.verify_model(str(model_name), reasoning_effort=effort),
                    }
                )
            text = str(model_checks[0].get("response_preview") or "")
            return {
                "status": "ok",
                "detail": "OpenAI provider verified successfully.",
                "provider": "openai",
                "model": default_model,
                "models_checked": model_checks,
                "response_preview": self._truncate_text(self._sanitize_text(text), 240),
            }
        except Exception as exc:
            return {
                "status": "error",
                "detail": str(exc),
                "provider": "openai",
                "model": default_model,
                "models_checked": model_checks,
                "response_preview": None,
            }

    def summarize_case(self, case_id: str, request: LlmSummaryRequest | dict[str, Any], actor: str = "system") -> LlmGeneratedOutput:
        payload = request if isinstance(request, LlmSummaryRequest) else LlmSummaryRequest.model_validate(request)
        return self._generate_output(
            case_id,
            task_type=payload.summary_kind,
            actor=actor,
            operator_instructions=payload.operator_instructions,
            escalate=payload.escalate,
            final_quality=payload.final_quality,
        )

    def summarize_timeline(self, case_id: str, request: dict[str, Any] | None = None, actor: str = "system") -> LlmGeneratedOutput:
        payload = dict(request or {})
        return self._generate_output(
            case_id,
            task_type="timeline_summary",
            actor=actor,
            operator_instructions=str(payload.get("operator_instructions") or "").strip(),
            escalate=bool(payload.get("escalate", False)),
            final_quality=bool(payload.get("final_quality", False)),
        )

    def summarize_evidence(self, case_id: str, request: dict[str, Any] | None = None, actor: str = "system") -> LlmGeneratedOutput:
        payload = dict(request or {})
        evidence_ids = [str(item).strip() for item in (payload.get("evidence_ids") or []) if str(item).strip()]
        return self._generate_output(
            case_id,
            task_type="evidence_summary",
            actor=actor,
            operator_instructions=str(payload.get("operator_instructions") or "").strip(),
            escalate=bool(payload.get("escalate", False)),
            final_quality=bool(payload.get("final_quality", False)),
            evidence_ids=evidence_ids,
        )

    def draft_report(self, case_id: str, request: dict[str, Any] | None = None, actor: str = "system") -> LlmGeneratedOutput:
        payload = dict(request or {})
        report_kind = str(payload.get("report_kind") or "draft_case_report").strip().lower()
        if report_kind not in {"draft_case_report", "operator_handoff_report"}:
            raise ValueError(f"Unsupported report kind '{report_kind}'")
        return self._generate_output(
            case_id,
            task_type=report_kind,
            actor=actor,
            operator_instructions=str(payload.get("operator_instructions") or "").strip(),
            escalate=bool(payload.get("escalate", False)),
            final_quality=bool(payload.get("final_quality", False)),
            persist_report=True,
            requested_format=str(payload.get("format") or "markdown").lower(),
        )

    def answer_case_query(self, case_id: str, question: str, request: dict[str, Any] | None = None, actor: str = "system") -> LlmGeneratedOutput:
        payload = dict(request or {})
        return self._generate_output(
            case_id,
            task_type="case_query",
            actor=actor,
            operator_instructions=str(payload.get("operator_instructions") or "").strip(),
            escalate=bool(payload.get("escalate", False)),
            final_quality=bool(payload.get("final_quality", False)),
            question=question,
        )

    def _generate_output(
        self,
        case_id: str,
        *,
        task_type: str,
        actor: str,
        operator_instructions: str = "",
        escalate: bool = False,
        final_quality: bool = False,
        evidence_ids: list[str] | None = None,
        persist_report: bool = False,
        requested_format: str = "markdown",
        question: str = "",
    ) -> LlmGeneratedOutput:
        if not bool(self._config.get("enabled", False)):
            raise RuntimeError("LLM intelligence layer is disabled.")
        case_context = self._build_case_context(case_id, evidence_ids=evidence_ids)
        insufficient = self._is_insufficient_context(task_type, case_context)
        selection = self._select_model(task_type, escalate=escalate, final_quality=final_quality)
        provider_name = str(selection["provider"])
        try:
            content = LLM_INSUFFICIENT_EVIDENCE_RESPONSE if insufficient else self._get_provider(provider_name).generate(
                self._build_prompt(task_type, case_context, operator_instructions=operator_instructions, question=question),
                context={
                    "task_type": task_type,
                    "case_id": case_id,
                    "case_context": case_context,
                    "question": question,
                    "instructions": self._build_instructions(task_type),
                    "model": selection["model"],
                    "reasoning_effort": selection["reasoning_effort"],
                    "max_output_tokens": selection["max_output_tokens"],
                    "insufficient_evidence": insufficient,
                },
            )
        except Exception:
            self._increment_metric("llm_failures_total")
            raise
        safe_content = self._finalize_output_text(
            content,
            task_type=task_type,
            case_context=case_context,
            as_markdown=persist_report and requested_format == "markdown",
        )
        output = LlmGeneratedOutput(
            case_id=case_id,
            task_type=task_type,
            content=safe_content,
            caveat=LLM_OPERATOR_REVIEW_CAVEAT,
            sources=[SourceReference.model_validate(item) for item in case_context["sources"]],
            provider=provider_name,
            model=selection["model"],
            reasoning_effort=selection["reasoning_effort"],
            used_fallback=bool(selection["used_fallback"]),
            safety_check_passed=self._passes_safety_checks(safe_content),
            metadata={
                "case_title": case_context["case"].get("title"),
                "evidence_count": len(case_context["evidence"]),
                "timeline_count": len(case_context["timeline"]),
                "notes_count": len(case_context["notes"]),
                "enrichment_source_count": len(case_context.get("enrichment_sources") or []),
                "enrichment_summary_count": len(case_context.get("enrichment_summaries") or []),
                "question": self._truncate_text(question, 240) if question else "",
                "requested_format": requested_format,
                "insufficient_evidence": insufficient,
            },
        )
        if persist_report and bool((self._config.get("reports") or {}).get("save_generated_reports", True)):
            report = self._persist_generated_report(output, actor=actor, requested_format=requested_format)
            output.report_id = report.export_id
            output.metadata["report_export_id"] = report.export_id
            output.metadata["report_type"] = report.report_type
        self._audit_generated_output(output, actor=actor)
        self._increment_metric("llm_requests_total")
        if output.report_id:
            self._increment_metric("llm_generated_reports_total")
        return output

    def _build_case_context(self, case_id: str, evidence_ids: list[str] | None = None) -> dict[str, Any]:
        case = self._case_service.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        safety_cfg = dict(self._config.get("safety") or {})
        max_evidence = int(safety_cfg.get("max_input_evidence_items") or 100)
        max_events = int(safety_cfg.get("max_input_events") or 100)
        max_notes = int(safety_cfg.get("max_notes") or 50)
        evidence = self._case_service.list_evidence(case_id)
        if evidence_ids:
            allowed = set(evidence_ids)
            evidence = [item for item in evidence if item.evidence_id in allowed]
        evidence = evidence[:max_evidence]
        timeline = self._case_service.get_timeline(case_id)[:max_events]
        notes = self._case_service.list_notes(case_id)[:max_notes]
        enrichment_sources, enrichment_summaries = self._load_enrichment_context(case_id, limit=max_notes)
        case_payload = {
            "case_id": case.case_id,
            "title": self._sanitize_text(case.title),
            "description": self._sanitize_text(case.description),
            "status": case.status,
            "priority": case.priority,
            "severity": case.severity,
            "camera_ids": list(case.camera_ids),
            "source_event_ids": list(case.source_event_ids)[:max_events],
            "track_ids": list(case.track_ids),
            "assigned_to": case.assigned_to,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
            "review_status": case.review_status,
            "requires_review": case.requires_review,
            "metadata": self._trim_metadata(case.metadata),
        }
        evidence_payload = [
            {
                "evidence_id": item.evidence_id,
                "evidence_type": item.evidence_type,
                "title": self._sanitize_text(item.title),
                "description": self._sanitize_text(item.description),
                "source_event_id": item.source_event_id,
                "camera_id": item.camera_id,
                "track_ids": list(item.track_ids),
                "timestamp": item.timestamp,
                "integrity_status": item.integrity_status,
                "hash_verified": item.hash_verified,
                "has_storage_artifact": bool(item.storage_uri or item.snapshot_uri),
                "metadata": self._trim_metadata(item.metadata),
            }
            for item in evidence
        ]
        timeline_payload = [
            {
                "timeline_id": item.timeline_id,
                "timestamp": item.timestamp,
                "type": item.type,
                "title": self._sanitize_text(item.title),
                "description": self._sanitize_text(item.description),
                "severity": item.severity,
                "source_id": item.source_id,
                "metadata": self._trim_metadata(item.metadata),
            }
            for item in timeline
        ]
        notes_payload = [
            {
                "note_id": item.note_id,
                "created_at": item.created_at,
                "created_by": item.created_by,
                "note": self._sanitize_text(item.note),
            }
            for item in notes
        ]
        enrichment_sources_payload = [
            {
                "source_id": item.source_id,
                "source_type": item.source_type,
                "title": self._sanitize_text(item.title),
                "description": self._sanitize_text(item.description),
                "source_reliability": item.source_reliability,
                "domain": str((item.metadata or {}).get("domain") or ""),
                "analyst_provided": item.analyst_provided,
                "created_by": item.created_by,
                "created_at": item.created_at,
                "summary": self._sanitize_text(item.summary),
                "requires_review": item.requires_review,
                "metadata": self._trim_metadata(item.metadata),
                "has_uploaded_artifact": bool(item.storage_uri),
            }
            for item in enrichment_sources
        ]
        enrichment_summaries_payload = [
            {
                "summary_id": item.summary_id,
                "source_ids": list(item.source_ids),
                "summary": self._sanitize_text(item.summary),
                "key_points": [self._sanitize_text(point) for point in item.key_points],
                "limitations": [self._sanitize_text(point) for point in item.limitations],
                "operator_review_caveat": self._sanitize_text(item.operator_review_caveat),
                "provider": item.provider,
                "model": item.model,
                "created_by": item.created_by,
                "created_at": item.created_at,
                "metadata": self._trim_metadata(item.metadata),
            }
            for item in enrichment_summaries
        ]
        return {
            "case": case_payload,
            "evidence": evidence_payload,
            "timeline": timeline_payload,
            "notes": notes_payload,
            "enrichment_sources": enrichment_sources_payload,
            "enrichment_summaries": enrichment_summaries_payload,
            "sources": self._build_sources(
                case_payload,
                evidence_payload,
                timeline_payload,
                enrichment_sources_payload,
                enrichment_summaries_payload,
            ),
        }

    def _build_sources(
        self,
        case_payload: dict[str, Any],
        evidence_payload: list[dict[str, Any]],
        timeline_payload: list[dict[str, Any]],
        enrichment_sources_payload: list[dict[str, Any]],
        enrichment_summaries_payload: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = [
            {
                "type": "case",
                "id": str(case_payload["case_id"]),
                "label": "Case metadata",
            }
        ]
        seen = {("case", str(case_payload["case_id"]))}
        for item in evidence_payload:
            key = ("evidence", str(item["evidence_id"]))
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "type": "evidence",
                    "id": str(item["evidence_id"]),
                    "label": item.get("title") or "Evidence item",
                }
            )
        for item in timeline_payload:
            key = ("timeline", str(item["timeline_id"]))
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "type": "timeline",
                    "id": str(item["timeline_id"]),
                    "label": item.get("title") or "Timeline item",
                }
            )
        for item in enrichment_sources_payload:
            key = ("external_source", str(item["source_id"]))
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "type": "external_source",
                    "id": str(item["source_id"]),
                    "label": item.get("title") or "Analyst-provided enrichment",
                }
            )
        for item in enrichment_summaries_payload:
            key = ("enrichment_summary", str(item["summary_id"]))
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "type": "enrichment_summary",
                    "id": str(item["summary_id"]),
                    "label": "Enrichment summary",
                }
            )
        return sources

    def _select_model(self, task_type: str, *, escalate: bool, final_quality: bool) -> dict[str, Any]:
        status = self.status()
        if _is_test_environment():
            return {
                "provider": "local_stub",
                "model": "local_stub",
                "reasoning_effort": "low",
                "max_output_tokens": 512,
                "used_fallback": False,
            }
        provider_name = str(status["provider"])
        active_provider = str(status["active_provider"])
        openai_cfg = dict((self._config.get("providers") or {}).get("openai") or {})
        reasoning_cfg = dict(openai_cfg.get("reasoning") or {})
        cost_cfg = dict(openai_cfg.get("cost_control") or {})
        require_explicit_escalation = bool(cost_cfg.get("require_explicit_escalation", True))
        allow_final_report_model = bool(cost_cfg.get("allow_final_report_model", True))

        if provider_name == "openai" and status["openai_key_present"]:
            provider = "openai"
            used_fallback = False
        elif active_provider == "local_stub":
            provider = "local_stub"
            used_fallback = provider_name != "local_stub"
        else:
            raise RuntimeError(status["detail"])

        if provider == "local_stub":
            return {
                "provider": provider,
                "model": "local_stub",
                "reasoning_effort": "low",
                "max_output_tokens": 512,
                "used_fallback": used_fallback,
            }

        default_model = self._resolve_openai_model("default")
        escalation_model = self._resolve_openai_model("escalation")
        final_report_model = self._resolve_openai_model("final_report")
        if task_type in {"draft_case_report", "operator_handoff_report"}:
            model_name = escalation_model
            reasoning_effort = str(reasoning_cfg.get("escalation_effort") or "medium")
            if final_quality and allow_final_report_model:
                model_name = final_report_model
                reasoning_effort = str(reasoning_cfg.get("final_report_effort") or "medium")
        elif escalate and require_explicit_escalation:
            model_name = escalation_model
            reasoning_effort = str(reasoning_cfg.get("escalation_effort") or "medium")
        else:
            model_name = default_model
            reasoning_effort = str(reasoning_cfg.get("default_effort") or "low")

        return {
            "provider": provider,
            "model": model_name,
            "reasoning_effort": reasoning_effort,
            "max_output_tokens": int(cost_cfg.get("max_output_tokens") or 1800),
            "used_fallback": used_fallback,
        }

    def _resolve_openai_model(self, model_kind: str) -> str:
        providers = dict(self._config.get("providers") or {})
        openai_cfg = dict(providers.get("openai") or {})
        if model_kind == "default":
            env_name = str(openai_cfg.get("model_env") or "OPENAI_LLM_MODEL")
            fallback = str(openai_cfg.get("model") or "gpt-5.4-mini")
        elif model_kind == "escalation":
            env_name = str(openai_cfg.get("escalation_model_env") or "OPENAI_LLM_ESCALATION_MODEL")
            fallback = str(openai_cfg.get("escalation_model") or "gpt-5.4")
        elif model_kind == "final_report":
            env_name = str(openai_cfg.get("final_report_model_env") or "OPENAI_LLM_FINAL_REPORT_MODEL")
            fallback = str(openai_cfg.get("final_report_model") or "gpt-5.5")
        else:
            raise ValueError(f"Unsupported model kind '{model_kind}'")
        return str(os.getenv(env_name, "").strip() or fallback)

    def _build_prompt(
        self,
        task_type: str,
        case_context: dict[str, Any],
        *,
        operator_instructions: str = "",
        question: str = "",
    ) -> str:
        task_lines = {
            "case_summary": "Generate a concise case summary based only on the supplied case context.",
            "incident_summary": "Generate an incident-focused summary based only on the supplied case context.",
            "timeline_summary": "Generate a concise timeline summary from the supplied ordered timeline items.",
            "evidence_summary": "Explain what the supplied evidence suggests without going beyond the provided records.",
            "draft_case_report": "Draft a polished markdown case report grounded only in the supplied case context.",
            "operator_handoff_report": "Draft a markdown operator handoff report with clear next actions grounded only in the supplied case context.",
            "case_query": "Answer the operator question using only the supplied case context.",
        }
        prompt = [
            f"Task: {task_lines.get(task_type, 'Generate a grounded case analysis draft.')}",
        ]
        if operator_instructions:
            prompt.extend(["", f"Operator instructions: {self._sanitize_text(operator_instructions)}"])
        if question:
            prompt.extend(["", f"Operator question: {self._sanitize_text(question)}"])
        prompt.extend(
            [
                "",
                "Case context JSON:",
                json.dumps(case_context, ensure_ascii=True, sort_keys=True),
            ]
        )
        return "\n".join(prompt)

    @staticmethod
    def _build_instructions(task_type: str) -> str:
        format_hint = "Return markdown." if task_type in {"draft_case_report", "operator_handoff_report"} else "Return plain text."
        return (
            "You generate source-grounded analyst drafts for a safety-sensitive case management system. "
            "Use only the supplied case context. If the supplied context does not support an answer, respond with "
            f"'{LLM_INSUFFICIENT_EVIDENCE_RESPONSE}'. "
            "Do not confirm identity, criminality, guilt, or unsupported certainty. "
            "Use careful language such as possible, observed, associated, or operator review required. "
            "Any enrichment context is analyst-provided only and is not independently verified. "
            "Do not reveal secrets, raw embeddings, file paths, or hidden metadata. "
            f"{format_hint}"
        )

    def _finalize_output_text(
        self,
        text: str,
        *,
        task_type: str,
        case_context: dict[str, Any],
        as_markdown: bool,
    ) -> str:
        body = self._sanitize_text(text)
        if not body:
            body = LLM_INSUFFICIENT_EVIDENCE_RESPONSE
        if as_markdown:
            body = self._render_report_markdown(body, task_type=task_type, case_context=case_context)
        if not body.startswith(LLM_OPERATOR_REVIEW_CAVEAT):
            separator = "\n\n" if as_markdown else "\n\n"
            body = f"{LLM_OPERATOR_REVIEW_CAVEAT}{separator}{body}"
        return body.strip()

    def _render_report_markdown(self, body: str, *, task_type: str, case_context: dict[str, Any]) -> str:
        reports_cfg = dict(self._config.get("reports") or {})
        case_payload = case_context["case"]
        lines = [body.strip()]
        if reports_cfg.get("include_case_ids", True):
            lines.extend(["", "## Case Reference", f"- Case ID: {case_payload.get('case_id')}"])
        if reports_cfg.get("include_evidence_ids", True):
            lines.extend(["", "## Evidence References"])
            if case_context["evidence"]:
                for item in case_context["evidence"]:
                    lines.append(
                        f"- {item.get('evidence_id')}: {item.get('title') or item.get('evidence_type')}"
                    )
            else:
                lines.append("- No evidence references were available.")
        if reports_cfg.get("include_timeline", True):
            lines.extend(["", "## Timeline References"])
            if case_context["timeline"]:
                for item in case_context["timeline"]:
                    lines.append(
                        f"- {item.get('timeline_id')}: {item.get('timestamp')} | {item.get('title') or item.get('type')}"
                    )
            else:
                lines.append("- No timeline references were available.")
        if case_context.get("enrichment_sources"):
            lines.extend(["", "## Analyst-Provided Enrichment"])
            for item in case_context["enrichment_sources"]:
                lines.append(
                    f"- {item.get('source_id')}: {item.get('title') or 'Manual source'} | "
                    f"{item.get('source_type')} | reliability={item.get('source_reliability')}"
                )
        if case_context.get("enrichment_summaries"):
            lines.extend(["", "## Enrichment Summaries"])
            for item in case_context["enrichment_summaries"]:
                lines.append(
                    f"- {item.get('summary_id')}: {item.get('summary') or 'No summary provided.'}"
                )
        if reports_cfg.get("include_model_caveats", True):
            lines.extend(
                [
                    "",
                    "## Model Caveats",
                    "- AI-assisted draft",
                    "- Requires operator review",
                    "- Source-grounded summary",
                    "- Safety check passed",
                ]
            )
        return "\n".join(lines).strip()

    def _persist_generated_report(self, output: LlmGeneratedOutput, *, actor: str, requested_format: str) -> CaseExport:
        if requested_format != "markdown":
            raise ValueError("Only markdown report persistence is currently supported")
        report = CaseExport(
            case_id=str(output.case_id),
            format="markdown",
            report_type=output.task_type,
            content=output.content,
            generated_at=output.generated_at,
            generated_by=actor,
            metadata={
                "provider": output.provider,
                "model": output.model,
                "reasoning_effort": output.reasoning_effort,
                "source_count": len(output.sources),
                "safety_check_passed": output.safety_check_passed,
            },
        )
        self._case_service.repository.add_report(report)
        return report

    def _audit_generated_output(self, output: LlmGeneratedOutput, *, actor: str) -> None:
        try:
            self._audit_service.record(
                f"llm_{output.task_type}_generated",
                resource_type="case",
                resource_id=output.case_id,
                detail=f"Generated {output.task_type} draft.",
                metadata={
                    "actor": actor,
                    "provider": output.provider,
                    "model": output.model,
                    "task_type": output.task_type,
                    "report_id": output.report_id,
                    "source_count": len(output.sources),
                    "used_fallback": output.used_fallback,
                    "safety_check_passed": output.safety_check_passed,
                },
            )
        except Exception:
            pass

    @staticmethod
    def _is_insufficient_context(task_type: str, case_context: dict[str, Any]) -> bool:
        evidence = list(case_context.get("evidence") or [])
        timeline = list(case_context.get("timeline") or [])
        enrichment_sources = list(case_context.get("enrichment_sources") or [])
        enrichment_summaries = list(case_context.get("enrichment_summaries") or [])
        if task_type == "evidence_summary":
            return not evidence
        if task_type == "case_query":
            return not evidence and len(timeline) <= 1 and not enrichment_sources and not enrichment_summaries
        return False

    def _load_enrichment_context(self, case_id: str, *, limit: int) -> tuple[list[Any], list[Any]]:
        try:
            from app.services.osint_service import get_osint_service

            service = get_osint_service()
            if not service.health().get("enabled", False):
                return [], []
            return (
                service.list_sources(case_id)[: max(0, limit)],
                service.list_summaries(case_id)[: max(0, limit)],
            )
        except Exception:
            return [], []

    @staticmethod
    def _sanitize_text(value: str | None) -> str:
        cleaned = SECRET_PATTERN.sub("[redacted]", str(value or "")).strip()
        for pattern, replacement in PROHIBITED_REWRITES:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned

    def _passes_safety_checks(self, value: str) -> bool:
        if not str(value or "").startswith(LLM_OPERATOR_REVIEW_CAVEAT):
            return False
        if SECRET_PATTERN.search(value or ""):
            return False
        return self._sanitize_text(value) == value

    def _trim_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        cleaned = safe_evidence_metadata(metadata or {})
        limited: dict[str, Any] = {}
        for index, (key, value) in enumerate(cleaned.items()):
            if index >= 12:
                break
            limited[str(key)] = self._trim_value(value)
        return limited

    def _trim_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._trim_value(item) for key, item in list(value.items())[:8]}
        if isinstance(value, list):
            return [self._trim_value(item) for item in value[:8]]
        if isinstance(value, str):
            return self._truncate_text(self._sanitize_text(value), 320)
        return value

    @staticmethod
    def _truncate_text(value: str, length: int) -> str:
        text = str(value or "").strip()
        if len(text) <= length:
            return text
        return text[: max(0, length - 3)].rstrip() + "..."

    def _get_provider(self, name: str):
        if name in self._providers:
            return self._providers[name]
        providers = dict(self._config.get("providers") or {})
        if name == "local_stub":
            provider = LocalStubProvider(dict(providers.get("local_stub") or {}))
        elif name == "openai":
            openai_cfg = dict(providers.get("openai") or {})
            merged_cfg = {
                **openai_cfg,
                "cost_control": dict(openai_cfg.get("cost_control") or {}),
                "reasoning": dict(openai_cfg.get("reasoning") or {}),
            }
            provider = OpenAIResponsesProvider(merged_cfg)
        else:
            raise ValueError(f"Unsupported LLM provider '{name}'")
        self._providers[name] = provider
        return provider

    @staticmethod
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


def get_llm_service() -> LlmService:
    global _LLM_SERVICE
    if _LLM_SERVICE is None:
        with _LLM_SERVICE_LOCK:
            if _LLM_SERVICE is None:
                _LLM_SERVICE = LlmService()
    return _LLM_SERVICE


def reset_llm_service() -> None:
    global _LLM_SERVICE
    with _LLM_SERVICE_LOCK:
        _LLM_SERVICE = None
    reset_llm_config()
