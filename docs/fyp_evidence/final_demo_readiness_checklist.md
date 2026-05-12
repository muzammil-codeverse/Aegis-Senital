# Final Demo Readiness Checklist

## Verified Local Readiness

- [x] Backend and frontend source trees are present and buildable from the repository workspace.
- [x] Project `.venv` resolves to Python `3.12.10`.
- [x] CUDA is available on the local RTX 4060 runtime.
- [x] Core promoted model assets are present: `models/phone/current.pt`, `models/weapon/current.pt`, `models/anomaly/violence_yolo11.pt`, `models/anomaly/current/`, `models/buffalo_l/`, `models/open_vocab/`, and `sam2_t.pt`.
- [x] `python scripts/validate_runtime.py --profile development` passes required development checks.
- [x] Model asset smoke passes for phone YOLO, weapon YOLO, violence YOLO, VideoMAE anomaly, InsightFace `buffalo_l`, ReID OSNet, Ultralytics SAM2, and configured open-vocab runtime.
- [x] Backend runtime/API smoke reaches dashboard, GIS, investigation graph, drone simulation status, drone missions, drone fusion health, analytics, model governance, cases, uploaded videos, and LLM status endpoints.
- [x] Investigation path reconstruction smoke runs with demo GIS profiles and returns an honest `insufficient_data` result when no geo-backed observations exist.
- [x] Deterministic drone-fusion smoke passes with safe wording and operator-review requirements intact.
- [x] Uploaded-video workflow smoke completes with a local sample clip.
- [x] LLM case workflow smoke completes with operator-review caveats and source references.
- [x] Safe wording static guardrails remain active.
- [x] Accessibility static guardrails remain active.
- [x] Frontend validation passes locally: `npm run test` (`76/76`), `npm run build`, and `npm run e2e` (`60 passed`, `3 skipped` optional live-drone checks).
- [x] `local_mock` GIS rendering path works without a paid map token.
- [x] Model governance and analytics views render in browser validation.
- [x] Optional live drone validation re-passed against a running Cosys-AirSim Blocks runtime.

## Demo-Day Checks

- [ ] Start backend before the live walkthrough.
- [ ] Start frontend before the live walkthrough.
- [ ] Confirm `.venv` is active in the demo terminal session.
- [ ] Re-run `python scripts/validate_runtime.py --profile development` if the environment changed.
- [ ] Re-run `npm run test`, `npm run build`, and `npm run e2e` from `frontend/` before the final presentation build is frozen.
- [ ] Confirm GIS is using `local_mock` unless a paid map token is intentionally configured.
- [ ] Confirm model governance pages render and show the current registry/governance state.
- [ ] Confirm analytics overview renders and reflects current local data.
- [ ] Confirm uploaded-video workflow uses a known local sample clip.
- [ ] Confirm case/evidence workflow and LLM-safe draft reporting are reachable from the UI.

## Optional Live Drone Demo

- [ ] Launch Cosys-AirSim Blocks only if the aerial demo segment is included.
- [ ] Re-run `python scripts/verify_drone_sim_runtime.py --strict` after Blocks starts.
- [ ] Re-run live drone smoke commands only if the simulator is reachable.
- [ ] Keep all aerial wording explicitly simulated: `Simulated drone feed`, `Simulated aerial observation`, and `Operator review required`.

## Notes

- Development readiness is currently suitable for a final FYP demo.
- Production readiness is not implied by this checklist; see `production_readiness_matrix.md`.
- Model governance remains visible in development even when production-only evidence, such as a live anomaly evaluation report, is still incomplete.
