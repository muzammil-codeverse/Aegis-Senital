# Operator Workflow Walkthrough

Date prepared: May 12, 2026

## Command-center flow
1. Open `#dashboard` for the operational overview, runtime strip, review queue, and timeline.
2. Use `Ctrl+K` to jump directly to routes, cases, cameras, alerts, drone missions, fusion correlations, model entries, or identity candidates that the current role can access.
3. Use grouped navigation to move between live operations, geospatial review, drone operations, and intelligence workflows without losing context.

## Drone workflow
1. Open `#drone-operations` to confirm simulator status, current telemetry, mission summary, and pending fusion reviews.
2. Open `#drone-simulation` to verify the live simulated aerial observation source.
3. Open `#drone-mission-planner` to create or monitor a simulated patrol mission.
4. Open `#drone-fusion` to review candidate cross-source observations, confidence breakdowns, and map handoff options.

## Investigation workflow
1. Open `#investigation` to review evidence-backed hypotheses and camera-graph context.
2. Use the safe wording banner and review controls to keep low-confidence or incomplete hypotheses in an operator-reviewed state.
3. Jump to `#map-operations` for spatial context when path review requires camera coverage or route geometry.

## Case and evidence workflow
1. Open `#cases` to review open cases, manual intake, and AI-assisted draft status.
2. Use the case drawer for evidence, notes, assignment, and enrichment context.
3. Use the map link to move from a case into `#map-operations` without exposing unrelated records.

## Uploaded video workflow
1. Open `#uploaded-video-analysis` to review offline uploads and resulting session state.
2. Use cases or the review queue to route qualifying findings into operator-reviewed case handling.

## Safety workflow
- Simulated drone sources are explicitly labeled as simulated.
- Candidate cross-source observations remain operator-reviewed.
- Identity, guilt, and target certainty claims are not surfaced in the frontend.

## Screenshot placeholder list
- Dashboard hero and runtime strip
- Drone Operations Hub overview
- Drone Fusion review workspace
- Investigation Workspace with command header
- Map Operations command header and overlays
- Cases workflow drawer
