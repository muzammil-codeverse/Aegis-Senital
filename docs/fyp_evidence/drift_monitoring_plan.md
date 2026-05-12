# Drift monitoring plan (Phase 41)

## Inputs (existing telemetry)

- Detection / incident / bus-backed events via `AnalyticsRepository.get_events` (confidence, coarse class labels, camera ids when present).
- Optional latency fields when emitted on events.
- Future: case dismissals / false-positive labels when persisted in analytics stores.

## Outputs

Per-model JSON summaries with:

- `sample_count`, `confidence_distribution` (histogram bins), `class_distribution`, `latency` aggregates, `per_camera_detection_counts`.
- `drift_status`: `insufficient_data` when no or too few samples — **never** invent a stable label without evidence.
- `recommendations`: operator-facing strings only when signals justify them.

## Storage

Configured directory `storage/model_drift` (created on demand); drift JSON snapshots can be added in later phases without changing governance contracts.
