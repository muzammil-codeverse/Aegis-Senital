#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _case_config(workdir: Path) -> dict:
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(workdir / "cases")},
            "evidence": {"max_items_per_case": 10},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def _llm_config(provider_name: str) -> dict:
    return {
        "llm": {
            "enabled": True,
            "provider": provider_name,
            "mode": "assistive_only",
            "default_provider": provider_name,
            "providers": {
                "local_stub": {"enabled": True},
                "openai": {
                    "enabled": True,
                    "api_key_env": "OPENAI_API_KEY",
                    "model_env": "OPENAI_LLM_MODEL",
                    "escalation_model_env": "OPENAI_LLM_ESCALATION_MODEL",
                    "final_report_model_env": "OPENAI_LLM_FINAL_REPORT_MODEL",
                    "model": "gpt-5.4-mini",
                    "escalation_model": "gpt-5.4",
                    "final_report_model": "gpt-5.5",
                    "timeout_seconds": 45,
                    "max_retries": 1,
                    "reasoning": {
                        "default_effort": "low",
                        "escalation_effort": "medium",
                        "final_report_effort": "medium",
                    },
                    "cost_control": {
                        "max_input_tokens": 120000,
                        "max_output_tokens": 1800,
                        "allow_final_report_model": True,
                        "require_explicit_escalation": True,
                    },
                },
            },
            "safety": {
                "max_input_events": 100,
                "max_input_evidence_items": 100,
                "max_notes": 50,
            },
            "reports": {
                "default_format": "markdown",
                "include_evidence_ids": True,
                "include_case_ids": True,
                "include_model_caveats": True,
                "include_timeline": True,
                "save_generated_reports": True,
            },
            "development": {"allow_local_stub_if_openai_key_missing": True},
            "production": {
                "fail_if_enabled_provider_missing": True,
                "fail_if_openai_key_missing": True,
            },
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the LLM case workflow.")
    parser.add_argument("--provider", choices=("local_stub", "openai"), default="local_stub")
    args = parser.parse_args()

    from app.services.audit_log_service import AuditLogService
    from app.services.case_service import CaseService
    from app.repositories.case_repository import JsonlCaseRepository
    from app.services.llm_service import LlmService, LLM_OPERATOR_REVIEW_CAVEAT

    if args.provider == "openai" and not str(__import__("os").environ.get("OPENAI_API_KEY", "")).strip():
        print("OpenAI smoke test skipped because OPENAI_API_KEY is missing.")
        return 0

    workdir = ROOT / "storage" / "smoke_llm_workflow"
    workdir.mkdir(parents=True, exist_ok=True)
    repo = JsonlCaseRepository(config=_case_config(workdir))
    case_service = CaseService(repository=repo, config=_case_config(workdir))
    audit_service = AuditLogService(
        config={
            "enabled": True,
            "storage_dir": str((workdir / "audit").relative_to(ROOT).as_posix()),
            "rotate_daily": False,
            "max_recent_entries": 500,
            "hash_chain_enabled": True,
        }
    )
    llm_service = LlmService(config=_llm_config(args.provider), case_service=case_service, audit_service=audit_service)

    case = case_service.create_case(
        {
            "title": "Synthetic safety review case",
            "description": "Synthetic case for smoke workflow verification.",
            "severity": "high",
            "priority": "high",
            "camera_ids": ["cam-smoke-1"],
        },
        actor="smoke-test",
    )
    case_service.add_evidence(
        case.case_id,
        {
            "evidence_type": "event",
            "title": "Synthetic event evidence",
            "description": "Synthetic evidence metadata for smoke validation.",
            "source_event_id": "evt_smoke_001",
            "metadata": {"summary": "Synthetic summary text", "display_label": "Synthetic event"},
        },
        actor="smoke-test",
    )
    case_service.add_note(case.case_id, {"note": "Synthetic operator note."}, actor="smoke-test")

    timeline = case_service.get_timeline(case.case_id)
    if not timeline:
        print("Smoke test failed: timeline did not build.")
        return 1

    summary = llm_service.summarize_case(case.case_id, {"summary_kind": "case_summary"}, actor="smoke-test")
    evidence_summary = llm_service.summarize_evidence(case.case_id, {}, actor="smoke-test")
    report = llm_service.draft_report(case.case_id, {"report_kind": "draft_case_report"}, actor="smoke-test")
    query = llm_service.answer_case_query(case.case_id, "What does the synthetic evidence show?", actor="smoke-test")

    outputs = [summary, evidence_summary, report, query]
    if not all(item.sources for item in outputs):
        print("Smoke test failed: one or more outputs are missing source references.")
        return 1
    if not all(item.content.startswith(LLM_OPERATOR_REVIEW_CAVEAT) for item in outputs):
        print("Smoke test failed: one or more outputs are missing the operator-review caveat.")
        return 1

    recent_audit = audit_service.get_recent(limit=20)
    llm_audit_entries = [item for item in recent_audit if str(item.get("action", "")).startswith("llm_")]
    if len(llm_audit_entries) < 4:
        print("Smoke test failed: expected LLM audit log entries were not written.")
        return 1

    print(f"Smoke workflow ok with provider={args.provider}")
    print(f"Case ID: {case.case_id}")
    print(f"Timeline items: {len(timeline)}")
    print(f"Source references: {len(summary.sources)}")
    print(f"Audit entries: {len(llm_audit_entries)}")
    return 0
