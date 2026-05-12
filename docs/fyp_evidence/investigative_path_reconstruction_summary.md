# Investigative Path Reconstruction — Phase 43 Summary

## Overview

The Investigative Path Reconstruction Engine is a safety-critical component of Aegis Sentinel that assists operators in understanding possible movement patterns across camera coverage areas. It generates **investigative hypotheses**, not confirmed facts.

## What the Path Engine Does

1. Accepts a reconstruction request anchored to a case ID or event ID
2. Loads authorized camera profiles and builds a directed camera graph
3. Collects event observations in the specified backward/forward time window
4. Filters unauthorized observations via object authorization
5. Scores camera-to-camera transitions by time consistency, geo distance, and travel feasibility
6. Generates up to N candidate path hypotheses with confidence breakdowns
7. Persists hypotheses for operator review
8. Returns safe-worded, operator-reviewable responses

## What the Path Engine Does NOT Claim

- It does **not** confirm identity
- It does **not** confirm criminality or guilt
- It does **not** confirm a subject was present at any location
- It does **not** fabricate evidence references — if no evidence refs exist, no hypothesis is generated
- It does **not** expose unauthorized camera, case, or event locations

## Safe Wording

All outputs use safe wording only:

- possible subject
- possible movement path
- candidate route
- investigative hypothesis
- operator review required
- evidence-backed hypothesis
- possible identity match

Forbidden wording blocked at generation:

- criminal confirmed
- suspect confirmed
- identity confirmed
- attacker confirmed
- guilty

## Scoring Factors

| Factor | Weight |
|---|---|
| Time consistency | 40% |
| Geo distance | 30% |
| Travel feasibility | 30% |
| Identity similarity | Optional bonus |
| Camera FOV continuity | Optional bonus |
| Event severity | Optional bonus |

## Evidence References

Each hypothesis includes `evidence_refs` listing the event or case IDs that justify the hypothesis. A hypothesis with zero evidence refs is blocked from being generated.

## Operator Review Workflow

1. Hypothesis generated with `review_status = pending`
2. Operator views hypothesis on Investigation Workspace
3. Operator accepts, rejects, or marks inconclusive
4. Review record is persisted with reviewer identity and timestamp
5. Audit event logged: `investigation_hypothesis_reviewed`

## Limitations

- Path reconstruction is probabilistic, not deterministic
- Camera graph edges are based on distance; actual routes may differ
- No biometric identification is performed
- Missing camera profiles reduce reconstruction quality
- Dev backend uses JSONL; production requires Postgres

## Connection to GIS and Drone Simulation

- Camera graph is built from GIS camera geo profiles
- FOV cones from GIS service inform edge scoring
- Geofence zones apply transition penalties
- Phase 44 drone simulation will add aerial observation nodes to the camera graph
