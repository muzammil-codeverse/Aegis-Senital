# Model governance summary (Phase 41)

This phase introduces **traceable model metadata**, **governance gates in `validate_runtime`**, **read-only governance APIs** with RBAC, **metadata-only rollback/promotion** (file registry writes must be explicitly enabled), **honest drift summaries** (no fabricated metrics), and **identity candidate emission** via the event bus.

## Why metrics are not fabricated

Runtime telemetry and evaluation outputs are stored only when produced by real pipelines or benchmarks. Empty `metrics` objects remain empty until an operator attaches benchmark evidence; promotion without metrics is rejected unless explicitly `exception_approved`.

## Live vs offline anomaly distinction

Offline VideoMAE checkpoints can show strong offline validation scores that reflect **pipeline validation**, not guaranteed live-site performance. Governance flags offline vs live evaluation requirements in `configs/runtime/model_governance.yaml` and registry `known_limitations`.

## Identity calibration and liveness

Face thresholds require calibration artifacts before production readiness; Re-ID requires benchmark evidence. **Liveness** is tracked as a governed provider entry with `status: disabled` until a real provider is integrated — never hidden.
