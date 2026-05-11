# Anomaly live validation (Phase 39)

This document describes the **live decoded-video** anomaly evaluation path. It contains no binary artifacts or per-run metrics; generate outputs locally under `storage/anomaly_live_eval/` (git-ignored).

## Command

```bash
python scripts/evaluate_anomaly_live_video.py \
  --videos datasets/test_videos \
  --model-path models/anomaly/current \
  --violence-model models/anomaly/violence_yolo11.pt \
  --device cuda \
  --output-dir storage/anomaly_live_eval
```

Optional manifest:

```bash
python scripts/evaluate_anomaly_live_video.py \
  --videos datasets/test_videos \
  --manifest configs/evaluation/anomaly_live_video_manifest.yaml \
  --model-path models/anomaly/current \
  --device cpu \
  --output-dir storage/anomaly_live_eval
```

## What it proves

- The VideoMAE adapter loads from `models/anomaly/current` and runs on **real decoded frames**.
- Optional violence YOLO weights are exercised when present.
- **Offline `_offline_predict` results are not live inference metrics.** The live script never calls the offline benchmark predictor.

## Caveats

- Frame budget is capped (`--max-frames`) for practicality; this is **limited validation**, not a full benchmark.
- Larger, diverse real-world evaluation remains future work (Phase 40+).

## Artifacts (local only)

| File | Purpose |
|------|---------|
| `metrics.json` | Aggregate latency and run counts |
| `report.md` | Human-readable sections including limitations |
| `per_video_predictions.jsonl` | One JSON object per input video |
| `latency_profile.json` | Per-video latency map |
