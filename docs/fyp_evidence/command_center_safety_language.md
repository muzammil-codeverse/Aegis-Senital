# Command Center Safety Language

Date prepared: May 12, 2026

## Policy
Frontend wording must avoid certainty claims that overstate what the system knows.

Preferred wording:
- Simulated drone feed
- Simulated aerial observation
- Candidate cross-source observation
- Possible movement path
- Operator review required
- Evidence-backed hypothesis
- Model limitation
- Insufficient data

## Frontend enforcement
- Static check:
  `scripts/check_frontend_safe_wording.py`
- Scope:
  `frontend/src`
- Result on May 12, 2026:
  PASS

## UI patterns used in Phase 47
- Drone pages label the simulator-backed source as simulated.
- Drone Fusion describes results as candidate observations and requires operator review.
- Investigation copy describes paths as possible or evidence-backed, never final.
- Command-center navigation and headers keep safety language visible rather than hiding it in tooltips only.

## Review expectations
- Operators remain responsible for accepting, rejecting, or marking cross-source outputs inconclusive.
- LLM-assisted outputs remain drafts with source-grounded review expectations.
- Frontend copy must not imply identity confirmation, guilt, or a real-world drone pursuit.
