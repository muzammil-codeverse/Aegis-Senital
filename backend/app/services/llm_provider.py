from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any


class LlmProvider(ABC):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    @abstractmethod
    def generate(self, prompt: str, *, context: dict | None = None) -> str:
        raise NotImplementedError


class LocalStubProvider(LlmProvider):
    def generate(self, prompt: str, *, context: dict | None = None) -> str:
        payload = context or {}
        task_type = str(payload.get("task_type") or "case_summary")
        case_context = dict(payload.get("case_context") or {})
        case_data = dict(case_context.get("case") or {})
        evidence = list(case_context.get("evidence") or [])
        timeline = list(case_context.get("timeline") or [])
        notes = list(case_context.get("notes") or [])
        question = str(payload.get("question") or "").strip()
        case_title = case_data.get("title") or case_data.get("case_id") or "the case"
        evidence_ids = [item.get("evidence_id") for item in evidence if item.get("evidence_id")]

        if payload.get("insufficient_evidence"):
            return "The available case evidence does not contain enough information to answer that."

        if task_type in {"case_summary", "incident_summary"}:
            return (
                f"Source-grounded summary for {case_title}: "
                f"{len(evidence)} evidence item(s), {len(timeline)} timeline item(s), and {len(notes)} note(s) were reviewed. "
                f"The case is currently marked {case_data.get('status', 'open')} with {case_data.get('severity', 'medium')} severity. "
                "Operator review is required before any operational action."
            )

        if task_type == "timeline_summary":
            first_timestamp = timeline[0].get("timestamp") if timeline else case_data.get("created_at")
            last_timestamp = timeline[-1].get("timestamp") if timeline else case_data.get("updated_at")
            return (
                f"Timeline summary for {case_title}: activity spans from {first_timestamp or 'the recorded start'} "
                f"to {last_timestamp or 'the latest update'}, with {len(timeline)} sequenced timeline item(s). "
                "Operator review is required for final interpretation."
            )

        if task_type == "evidence_summary":
            highlighted = ", ".join(evidence_ids[:3]) or "available evidence metadata"
            return (
                f"Evidence summary for {case_title}: {len(evidence)} evidence item(s) were reviewed. "
                f"Highlighted references: {highlighted}. Operator review is required for final interpretation."
            )

        if task_type == "operator_handoff_report":
            return (
                f"# Operator Handoff Report\n\n"
                f"## Current Status\n{case_title} remains in {case_data.get('status', 'open')} status.\n\n"
                f"## Evidence Overview\nReviewed {len(evidence)} evidence item(s) and {len(timeline)} timeline item(s).\n\n"
                "## Next Operator Actions\n- Validate the latest evidence references.\n- Confirm whether escalation is needed.\n"
            )

        if task_type == "draft_case_report":
            return (
                f"# Draft Case Report\n\n"
                f"## Overview\n{case_title} is a source-grounded case review draft.\n\n"
                f"## Findings\n- Evidence items reviewed: {len(evidence)}\n- Timeline items reviewed: {len(timeline)}\n- Operator notes reviewed: {len(notes)}\n\n"
                "## Assessment\nThe available system evidence supports continued operator review.\n"
            )

        if task_type == "case_query":
            return (
                f"Question: {question or 'No question provided.'}\n\n"
                f"Available grounded context for {case_title} includes {len(evidence)} evidence item(s), "
                f"{len(timeline)} timeline item(s), and {len(notes)} note(s). Operator review is required."
            )

        return "Source-grounded draft generated from available case context. Operator review is required."


class OpenAIResponsesProvider(LlmProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self._api_key_env = str(self._config.get("api_key_env") or "OPENAI_API_KEY")
        self._model_env = str(self._config.get("model_env") or "OPENAI_LLM_MODEL")
        self._escalation_model_env = str(self._config.get("escalation_model_env") or "OPENAI_LLM_ESCALATION_MODEL")
        self._final_report_model_env = str(self._config.get("final_report_model_env") or "OPENAI_LLM_FINAL_REPORT_MODEL")
        self._timeout_seconds = float(self._config.get("timeout_seconds") or 45)
        self._max_retries = max(0, int(self._config.get("max_retries") or 2))
        self._reasoning = dict(self._config.get("reasoning") or {})
        self._cost_control = dict(self._config.get("cost_control") or {})
        self._client = None

    def _resolve_api_key(self) -> str:
        api_key = os.getenv(self._api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"{self._api_key_env} is required for the OpenAI provider")
        return api_key

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("openai package is not installed") from exc
        self._client = OpenAI(
            api_key=self._resolve_api_key(),
            timeout=self._timeout_seconds,
            max_retries=0,
        )
        return self._client

    def resolve_model_name(self, model_kind: str = "default") -> str:
        if model_kind == "default":
            env_name = self._model_env
            fallback = str(self._config.get("model") or "gpt-5.4-mini")
        elif model_kind == "escalation":
            env_name = self._escalation_model_env
            fallback = str(self._config.get("escalation_model") or "gpt-5.4")
        elif model_kind == "final_report":
            env_name = self._final_report_model_env
            fallback = str(self._config.get("final_report_model") or "gpt-5.5")
        else:
            raise ValueError(f"Unsupported model kind '{model_kind}'")
        return str(os.getenv(env_name, "").strip() or fallback)

    def generate(self, prompt: str, *, context: dict | None = None) -> str:
        payload = context or {}
        model = str(payload.get("model") or self.resolve_model_name("default"))
        reasoning_effort = str(
            payload.get("reasoning_effort")
            or self._reasoning.get("default_effort")
            or "low"
        )
        instructions = str(payload.get("instructions") or "").strip() or None
        max_output_tokens = int(
            payload.get("max_output_tokens")
            or self._cost_control.get("max_output_tokens")
            or 1800
        )
        client = self._get_client()
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = client.responses.create(
                    model=model,
                    reasoning={"effort": reasoning_effort},
                    instructions=instructions,
                    input=prompt,
                    max_output_tokens=max_output_tokens,
                )
                text = getattr(response, "output_text", None) or self._extract_output_text(response)
                if text:
                    return text.strip()
                raise RuntimeError("OpenAI Responses API returned no text output")
            except Exception as exc:  # pragma: no cover - network/runtime dependent
                last_error = exc
                if attempt >= self._max_retries:
                    break
                time.sleep(min(2.0, 0.35 * (attempt + 1)))

        message = str(last_error)[:240] if last_error else "unknown provider failure"
        raise RuntimeError(f"OpenAI Responses API request failed: {message}")

    def verify_model(self, model_name: str, *, reasoning_effort: str = "low") -> dict[str, Any]:
        if not str(model_name or "").strip():
            raise RuntimeError("Model name is required for verification")
        model_name = str(model_name).strip()
        try:
            text = self.generate(
                "Respond with a short safe sentence confirming the model is available.",
                context={
                    "model": model_name,
                    "reasoning_effort": reasoning_effort,
                    "instructions": (
                        "You are verifying model availability for a safety-sensitive case analysis system. "
                        "Return one short sentence and do not mention secrets."
                    ),
                    "max_output_tokens": 120,
                },
            )
        except Exception as exc:
            raise RuntimeError(f"Model '{model_name}' verification failed: {exc}") from exc
        return {
            "model": model_name,
            "status": "ok",
            "response_preview": text.strip(),
        }

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", "") == "output_text":
                    text_value = getattr(content, "text", None)
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
        return "\n".join(parts).strip()


def llm_output_as_json(value: str) -> dict[str, Any]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Provider output is not valid JSON") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Provider output JSON must be an object")
    return loaded
