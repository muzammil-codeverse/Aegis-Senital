# Identity system summary (FYP evidence)

This document describes how identity-related subsystems work in Aegis Sentinel, what operators can rely on, and what must never be claimed.

## InsightFace (face appearance)

InsightFace (when installed and configured) produces face embeddings for **possible** appearance similarity. It does **not** establish legal identity, criminality, or intent. Low-quality detections should be rejected upstream; the UI and APIs use wording such as **low-quality face rejected** when quality gates fail.

## OSNet / ReID (person re-identification)

ReID models such as OSNet score similarity of person crops across cameras. Outputs are **identity candidates** or **possible identity matches** for analyst review. Rank metrics from offline benchmarks describe retrieval quality on a specific dataset only; they are not operational guarantees.

## Liveness / anti-spoofing

**Liveness** refers to signals that a live person was present at capture time. When `liveness.enabled` is `false`, the product must present **liveness disabled** (or equivalent). When enabled without an integrated provider, production readiness **fails** so the system never implies active anti-spoofing. The adapter does not return spoof-safe verdicts unless a real provider is registered.

## Operator review

Identity fusion may surface candidates. **Requires operator review** is mandatory language: there is no auto-confirmation of identity in production configuration (`auto_confirm_identity: false`). Review outcomes are audited (`identity_candidate_reviewed`, `identity_candidate_rejected`, `identity_candidate_escalated`).

## Calibrated vs not calibrated

Face thresholds and ReID operating points should be chosen using real calibration or benchmark datasets under `storage/identity_calibration/` (see `identity_calibration_guidance.md`). Missing calibration is surfaced in runtime health; production readiness may fail when `require_calibration_before_production` / `require_benchmark_before_production` are set.

## Limitations

- No subsystem confirms identity in a legal or investigative sense.
- Cross-camera linking is probabilistic and configuration-dependent.
- Liveness is optional and may be unavailable.

## Safe wording policy

Use: **possible identity match**, **identity candidate**, **requires operator review**, **liveness unavailable** / **liveness disabled**, **low-quality face rejected**.

Do not use: **identity confirmed**, **suspect confirmed**, **criminal identified**, or similar definitive claims.
