# Model Evaluation Guide — Phase 25

Aegis Sentinel Phase 25 introduces a reproducible model evaluation and benchmarking framework.
This document describes how to run evaluations, interpret results, and add new datasets.

---

## Quick Start

```bash
# Detection evaluation (CPU fallback)
python scripts/evaluate_models.py --task detection --device cpu

# Detection on specific dataset and model
python scripts/evaluate_models.py \
  --task detection \
  --config configs/evaluation/evaluation.yaml \
  --dataset weapon_eval \
  --model weapon_yolo \
  --device cuda

# Tracking evaluation
python scripts/evaluate_models.py --task tracking --dataset mot_eval

# Face recognition evaluation
python scripts/evaluate_models.py --task face --dataset face_eval

# ReID evaluation
python scripts/evaluate_models.py --task reid --dataset reid_eval

# Open-vocab evaluation
python scripts/evaluate_models.py --task open_vocab --dataset open_vocab_eval

# Latency profiling
python scripts/profile_runtime_latency.py \
  --input samples/videos/test_stream.mp4 \
  --duration-seconds 120 \
  --device cuda
```

---

## Configuration

### Primary Config

`configs/evaluation/evaluation.yaml` — main evaluation config.

Key sections:
- `evaluation.device` — cuda or cpu
- `evaluation.allow_cpu_fallback` — fall back to CPU if CUDA unavailable
- `evaluation.fail_on_missing_required_dataset` — fail hard on missing required datasets
- `regression_policy` — thresholds for comparison reports
- `models` — model name → path mapping
- `datasets` — dataset name → path mapping (populate per environment)

### Dataset Config

Copy `configs/evaluation/datasets.example.yaml` to a local file and fill in paths.
Do **not** commit real dataset paths to version control.

### Thresholds

`configs/evaluation/thresholds.yaml` — dataset-specific acceptance thresholds.
These are **not** operational deployment thresholds — they are evaluation targets.

---

## Task Reference

### Detection (weapon_yolo, phone_yolo)

Dataset format: YOLO (labels/*.txt + images/) or COCO JSON.

Metrics:
- `map_50` — mAP@IoU=0.5
- `map_50_95` — mAP@IoU=0.5:0.95 (not yet implemented — requires multi-threshold loop)
- `precision`, `recall`, `f1`
- `per_class_ap` — AP per class
- `false_positives_per_image`, `false_negatives_per_image`
- `iou_distribution` — mean/min/max IoU of matched detections

Artifacts:
- `per_class_metrics.csv`
- `failure_cases.jsonl`

### Tracking

Dataset format: MOTChallenge (gt/gt.txt + det/det.txt + img1/).

Metrics: `mota`, `motp`, `idf1`, `id_switches`, `avg_track_duration_frames`

Artifacts: `failure_cases.jsonl` (ID switch cases)

### Face Recognition (InsightFace)

Dataset format: LFW-style pairs.txt + images/identity_name/

Metrics:
- `far`, `frr` — at recommended threshold
- `tar_at_far_thresholds` — TAR at FAR=1e-1, 1e-2, 1e-3, 1e-4
- `recommended_threshold` — from data, not hardcoded

**Important:** The recommended threshold is dataset-specific.
Validate on held-out data before operational use.

Artifacts: `threshold_sweep.csv`

### ReID (OSNet)

Dataset format: Market-1501 style query/ + gallery/

Metrics: `rank_1`, `rank_5`, `map`, `cmc_curve`

Overlap detection: warns if same image appears in query and gallery.

### Open-Vocab (Grounding DINO)

Evaluate each prompt independently.

```yaml
open_vocab_eval:
  prompts:
    - prompt_id: weapon_visible
      text: "visible weapon"
      threshold: 0.35
    - prompt_id: firearm
      text: "firearm"
      threshold: 0.35
```

Metrics per prompt: `precision`, `recall`, `f1`, `avg_latency_ms`

Artifacts: `open_vocab_prompt_metrics.csv`

### Latency Profiling

Profiles per-stage latency over a video input.

Stages profiled:
- frame_decode, preprocessing, yolo_inference, open_vocab_inference,
  tracking, face_embedding, reid_embedding, identity_fusion,
  event_scoring, event_bus_publish, websocket_push

Artifacts: `latency_profile.json`, `gpu_profile.json`, `latency_report.md`

---

## Output Structure

Each run produces a timestamped directory under `storage/evaluation_runs/`:

```
storage/evaluation_runs/
  run_2026_05_09_120000_detection/
    config_snapshot.yaml      ← config at run time
    metrics.json              ← full run data
    report.md                 ← human-readable report
    per_class_metrics.csv     ← detection per-class AP
    failure_cases.jsonl       ← hard failure cases
    latency_profile.json      ← latency stages
    gpu_profile.json          ← GPU snapshot
    latency_report.md         ← latency summary
    threshold_sweep.csv       ← face threshold sweep
    open_vocab_prompt_metrics.csv ← per-prompt metrics
```

---

## Failure Cases

All evaluation tasks export failure cases to `failure_cases.jsonl`.

Format:
```json
{
  "task": "detection",
  "sample_id": "img_001",
  "frame_id": 0,
  "camera_id": null,
  "failure_type": "false_positive",
  "expected": {},
  "actual": {"class_id": 0, "score": 0.72},
  "confidence": 0.72,
  "notes": ""
}
```

Failure types: `false_positive`, `false_negative`, `id_switch`, `false_merge`, `false_split`, `latency_violation`

---

## Dataset Availability

If a dataset path does not exist:
- **required=true** → evaluation fails immediately with a clear error
- **required=false** → task is skipped with a warning in the report

Never silently ignore missing datasets. Always check the warnings section of reports.

---

## Safety Notes

- No fake detections or fabricated benchmark results are ever used.
- Evaluation predict_fn stubs return empty lists until real models are wired in.
- Face threshold recommendations are dataset-specific — not operational thresholds.
- Do not claim evaluation mAP = production accuracy without validation on deployment data.
