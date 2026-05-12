# Final System Capability Summary

Aegis Sentinel is currently capable of supporting a final FYP demo across the full local development stack with explicit safety wording and operator-review guardrails.

## Core Detection and Analysis

- Detection models: local phone and weapon detectors load from the promoted registry paths and run through the Ultralytics runtime.
- Anomaly detection: the promoted VideoMAE anomaly bundle loads locally, and the auxiliary `violence_yolo11.pt` checkpoint also loads.
- Segmentation: Ultralytics SAM2 loads from `sam2_t.pt` using the configured segmentation runtime.
- Identity and ReID: InsightFace `buffalo_l` and OSNet ReID runtime dependencies load locally for possible identity matching, with operator review required.
- Open-vocab search: configured GroundingDINO assets load locally when the open-vocab model path is present.

## Workflow Coverage

- Case and evidence workflow: local case creation, evidence attachment, and timeline assembly are available in development.
- LLM reporting: case summarization and draft reporting run with operator-review caveats, source references, and model limitation language.
- OSINT-safe enrichment: the current mode remains analyst-provided-only, which avoids unreviewed automated fetching.
- Uploaded video: local uploaded-video ingestion and processing complete against sample clips.
- Streaming: runtime configuration supports replay, HLS, and WebRTC development paths, with honest degraded reporting when external services are absent.
- Analytics: dashboard and analytics overview routes are reachable in local smoke validation.
- Model governance: registry, limitations, and validation endpoints remain visible so current model status and governance caveats are explicit.

## Geospatial and Investigation Features

- GIS: the system supports `local_mock` map configuration for demo use without a paid provider token.
- Investigation path reconstruction: the graph and path-reconstruction workflow runs with demo GIS profiles and reports `Insufficient data` rather than inventing movement claims.
- Command center UI: the frontend includes dashboard, GIS, drone, fusion, investigation, model governance, uploaded-video, analytics, and reporting surfaces introduced across prior phases.

## Simulated Aerial Features

- Drone simulation: backend status and runtime hooks are available for a simulated aerial feed.
- Drone mission planner: simulated mission planning and mission status APIs are present, with operator-start and simulated-only constraints.
- Drone fusion: deterministic fusion smoke demonstrates candidate cross-source observations with safe wording, operator review required, and no prohibited certainty claims.

## Validation Guardrails

- Safe wording checks remain active for phrases such as `Possible incident`, `Possible identity match`, `Candidate cross-source observation`, `Simulated drone feed`, `Operator review required`, `Evidence-backed hypothesis`, `Model limitation`, and `Insufficient data`.
- Frontend accessibility static checks remain part of the validation toolchain.
- Frontend performance and bundle-budget checks remain available for release gating.
- End-to-end and build validation remain available through the frontend test/build toolchain and should be rerun for the final frozen demo package.
