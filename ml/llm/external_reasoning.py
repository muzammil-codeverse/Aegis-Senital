from __future__ import annotations

from typing import Any


class ExternalReasoningEngine:
    """
    Optional explanation layer for scenario summaries and audit logs.

    This implementation is local and deterministic so it can be used even when
    no external LLM service is configured.
    """

    def explain(self, scenario: dict[str, Any], events: list[dict[str, Any]] | None = None) -> dict[str, str]:
        events = events or list(scenario.get("event_cluster", []))
        scenario_type = scenario.get("scenario_type", "UNKNOWN")
        risk_level = scenario.get("risk_level", "LOW")
        event_types = ", ".join(sorted({event.get("event_type", "UNKNOWN") for event in events})) or "none"
        explanation = (
            f"Scenario {scenario_type} was formed from {len(events)} persisted event(s): {event_types}."
        )
        risk_assessment = (
            f"Risk is {risk_level} based on correlated identities, spatial proximity, and temporal persistence."
        )
        reasoning_trace = (
            "events_persisted -> event_vectors_built -> cluster_formed -> scenario_classified"
        )
        return {
            "explanation": explanation,
            "risk_assessment": risk_assessment,
            "reasoning_trace": reasoning_trace,
        }
