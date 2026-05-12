# Final Known Limitations

- Public dataset limitations: offline model evaluation still reflects public or mirrored datasets more than site-specific production footage.
- Live camera validation scope: local demo validation proves runtime behavior, not broad real-world camera coverage across all deployment conditions.
- Drone simulation versus real drone distinction: all current drone flows are simulated and must remain labeled as `Simulated drone feed` or `Simulated aerial observation`.
- Production database and environment: local development does not currently provide a production-configured Postgres, Redis, fixed JWT secret, or OpenAI key.
- Model calibration limitations: identity thresholds and ReID benchmarking still require production-style calibration evidence before production claims should be made.
- Identity is not legal identification: identity outputs remain possible identity matches or operator-review candidates, not confirmed legal identification.
- LLM reports are drafts: generated summaries and reports are assistive drafts with operator review required.
- OSINT is analyst-provided only: no autonomous web-harvesting workflow is enabled in the current validated configuration.
- Map provider limitations: `local_mock` is the default safe demo provider when a paid token is not configured.
- Live AirSim dependency: live simulated aerial validation depends on the external Cosys-AirSim Blocks runtime being installed, launchable, and reachable.
- Governance evidence gap: development governance is currently degraded by missing production-style anomaly live-evaluation evidence, even though local demo runtime is operational.
