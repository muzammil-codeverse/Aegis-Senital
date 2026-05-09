# Benchmark Reports Guide — Phase 25

This document describes how to generate, read, and compare benchmark reports.

---

## Generating Reports

Every evaluation run automatically generates a versioned report bundle.

```bash
# Run evaluation (report auto-generated)
python scripts/evaluate_models.py --task detection --device cpu

# Compare two runs
python scripts/compare_benchmarks.py \
  --baseline storage/evaluation_runs/run_2026_05_09_120000_detection \
  --candidate storage/evaluation_runs/run_2026_05_09_180000_detection \
  --output storage/evaluation_runs/comparisons/compare_may_09.md
```

---

## Report Artifacts

| File | Description |
|------|-------------|
| `config_snapshot.yaml` | Full config at run time — reproducibility anchor |
| `metrics.json` | All metrics in structured JSON |
| `report.md` | Human-readable markdown summary |
| `per_class_metrics.csv` | Per-class AP for detection runs |
| `failure_cases.jsonl` | Hard cases for iterative dataset improvement |
| `latency_profile.json` | Per-stage latency (p50/p90/p95/p99/max) |
| `gpu_profile.json` | GPU memory and utilization snapshot |
| `latency_report.md` | Latency report in markdown |
| `threshold_sweep.csv` | Face FAR/FRR/TAR at each threshold |
| `open_vocab_prompt_metrics.csv` | Per-prompt precision/recall/F1/latency |

---

## Comparison Report

The comparison report (`compare_benchmarks.py`) shows:

| Metric | Baseline | Candidate | Change | % Change | Status |
|--------|----------|-----------|--------|----------|--------|
| detection.map_50 | 0.70 | 0.75 | +0.05 | +7.14% | ✓ improved |
| detection.false_positives_per_image | 0.8 | 0.6 | -0.2 | -25.0% | ✓ improved |
| latency.p95_ms | 85 | 110 | +25 | +29.4% | ✗ regressed |

### Regression Policy

Configurable thresholds determine pass/warn/fail:

```yaml
regression_policy:
  detection_map_drop_warn: 0.02     # warn if mAP drops by this amount
  detection_map_drop_fail: 0.05     # fail if mAP drops by this amount
  latency_p95_increase_warn_percent: 15   # warn if p95 increases by 15%
  latency_p95_increase_fail_percent: 30   # fail if p95 increases by 30%
  false_positive_increase_warn_percent: 20
```

Overall status: **pass** | **warn** | **fail**

---

## Metrics Reference

### Detection

| Metric | Description |
|--------|-------------|
| `map_50` | mAP at IoU=0.5 |
| `precision` | TP / (TP + FP) |
| `recall` | TP / (TP + FN) |
| `f1` | Harmonic mean of precision and recall |
| `per_class_ap` | AP per class |
| `false_positives_per_image` | Average FP count per image |

### Tracking

| Metric | Description |
|--------|-------------|
| `mota` | Multi-Object Tracking Accuracy |
| `motp` | Multi-Object Tracking Precision |
| `idf1` | Identity F1 Score |
| `id_switches` | Number of identity switches |

### Face

| Metric | Description |
|--------|-------------|
| `far` | False Accept Rate at recommended threshold |
| `frr` | False Reject Rate at recommended threshold |
| `tar_at_far_thresholds` | TAR at FAR=1e-1/1e-2/1e-3/1e-4 |
| `recommended_threshold` | Dataset-optimal threshold (not operational) |

### ReID

| Metric | Description |
|--------|-------------|
| `rank_1` | Rank-1 accuracy |
| `rank_5` | Rank-5 accuracy |
| `map` | Mean Average Precision |

### Open-Vocab (per prompt)

| Metric | Description |
|--------|-------------|
| `precision` | TP / (TP + FP) for this prompt |
| `recall` | TP / (TP + FN) for this prompt |
| `f1` | F1 for this prompt |
| `avg_latency_ms` | Inference latency per image |

### Latency

| Metric | Description |
|--------|-------------|
| `p50_ms` | Median latency |
| `p95_ms` | 95th percentile latency |
| `p99_ms` | 99th percentile latency |
| `avg_fps` | Average frames per second |
| `dropped_frames` | Frames dropped during profile |

---

## Failure Case Export

Failure cases enable targeted dataset curation.

Example use cases:
- Export FP cases → add hard negatives to training set
- Export FN cases → identify underrepresented object variants
- Export ID switch cases → identify tracking failure conditions

---

## Reproducibility

Each run saves `config_snapshot.yaml` capturing:
- model paths and versions
- dataset names
- device and inference settings
- evaluation thresholds

Combined with `git_commit`, this allows exact reproduction of any benchmark run.

---

## Next Steps

After Phase 25, Phase 26 will use this framework to:
- Compare YOLO11 / YOLO26 / RT-DETR / RF-DETR detectors
- Run head-to-head benchmarks with versioned reports
- Automate regression detection in CI
