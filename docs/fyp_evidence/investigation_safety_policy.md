# Investigation Safety Policy

## Purpose

This document defines the safety constraints governing all investigative path reconstruction outputs in Aegis Sentinel. These constraints are enforced at the service layer and must not be weakened.

## Mandatory Constraints

1. **No identity confirmation** — The system must never state that a specific person was identified, confirmed, or matched with certainty.
2. **No guilt language** — The system must never use: criminal confirmed, suspect confirmed, attacker confirmed, guilty, criminality confirmed.
3. **No fabricated evidence** — Path hypotheses must reference real, system-sourced event or case IDs. Hypotheses without evidence refs are blocked.
4. **Operator review required** — All hypotheses carry `operator_review_required: true`. No automated enforcement action may be taken.
5. **Object authorization** — Unauthorized cameras, cases, and events are filtered before path construction. No unauthorized location data is exposed.

## Enforcement Points

| Layer | Enforcement |
|---|---|
| `path_reconstruction_service.py` | Blocks forbidden phrases, requires evidence refs |
| `investigation_routes.py` | Requires `investigation:read` / `investigation:write` permissions |
| `security.yaml` | Role-to-permission mapping for investigation |
| `llm_service.py` | Injects safety notice into LLM context |
| Frontend `InvestigationSafetyBadge` | Visual reminder on all investigation UI |

## Review States

| State | Meaning |
|---|---|
| `pending` | Not yet reviewed by an operator |
| `accepted` | Operator has accepted as plausible |
| `rejected` | Operator has rejected as implausible or incorrect |
| `inconclusive` | Operator cannot determine reliability |

Accepted hypotheses do not become facts — they remain investigative aids.

## LLM Integration Safety

The LLM context includes:

```
"investigation_safety_notice": "Path hypotheses are investigative aids, not confirmed facts.
Do not state guilt, identity confirmation, or criminality.
Always use safe wording: 'possible movement path', 'investigative hypothesis', 'operator review required'."
```

LLM-generated reports citing path hypotheses must not restate them as confirmed movements.
