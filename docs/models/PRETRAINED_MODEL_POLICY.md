# Pretrained Model Policy — Aegis Sentinel

## 1. Purpose

This document defines rules for how pretrained model weights enter and remain in the Aegis Sentinel system. Every model used in production inference must satisfy the conditions in this policy.

---

## 2. Allowed Uses of Pretrained Weights

### 2.1 COCO-Pretrained YOLO (Ultralytics)

YOLO11 and YOLOv8 weights pretrained on COCO (e.g., `yolo11s.pt`, `yolo11m.pt`) **may be used as initialization** for fine-tuning on Aegis datasets. This is the standard and recommended starting point for all Aegis detection models.

- Source: Ultralytics GitHub releases / `ultralytics` Python package auto-download.
- These weights are **never used directly** for production inference; they only serve as a weight init for supervised fine-tuning.
- No license or redistribution concerns — Ultralytics AGPL-3.0 for source; weights are COCO-pretrained (public domain data).

### 2.2 Roboflow-Hosted Datasets

Datasets downloaded from Roboflow may be used **for training and evaluation only**. The dataset is downloaded, class-remapped via the active taxonomy alias table, and stored locally under `datasets/raw/` (gitignored).

- Roboflow **inference API is never called at runtime**. The system is not cloud-dependent for inference.
- Roboflow model exports (auto-train results) may be inspected or benchmarked locally but **must not be promoted to production** unless they go through the standard promotion pipeline.

---

## 3. Prohibited Uses

| Practice | Status | Reason |
|---|---|---|
| Roboflow cloud inference at runtime | **PROHIBITED** | External API dependency; outage = system failure |
| Black-box model from Roboflow auto-train in production | **PROHIBITED** | No class parity guarantee; unknown training data |
| Downloading model weights at runtime (no-artifact-on-disk) | **PROHIBITED** | Reproducibility and air-gap requirements |
| Models without a `metadata.yaml` in `models/` | **PROHIBITED** | Breaks `ModelRouter`, registry validation, and benchmark lineage |
| Weights in git history (`.pt`, `.onnx`) | **PROHIBITED** | Binary bloat; use DVC or Git LFS if versioning is required |

---

## 4. Production Model Requirements

Every model weight promoted to `models/{task}/current.pt` **must satisfy all of the following**:

1. **Local artifact**: the `.pt` or `.onnx` file exists on disk and is resolvable by `models/registry.json`.
2. **Metadata file**: `models/{task}/metadata.yaml` exists and records `task`, `active_weight`, `source_weight`, training summary, and dataset lineage.
3. **Registry entry**: `models/registry.json` has a `{task}` entry pointing to the correct `path` and `metadata` files.
4. **Class parity**: the model's class list matches the active taxonomy (`configs/taxonomy/weapon_taxonomy_v2.yaml` for weapon, `configs/evaluation/evaluation.local.yaml` for phone).
5. **Benchmark pass**: the model has been benchmarked on the `{task}_eval` dataset and meets the promotion thresholds below.

---

## 5. Promotion Thresholds

### Weapon v2 (YOLO11, 9-class)

| Metric | Minimum |
|---|---|
| mAP50 (all classes) | ≥ 0.50 |
| Recall (all classes) | ≥ 0.60 |
| Pistol AP50 | ≥ 0.50 |
| Rifle AP50 | ≥ 0.40 |
| Knife AP50 | ≥ 0.40 |
| p95 inference latency (GPU) | < 50 ms |

### Phone (YOLOv8, 2-class mapped to single "phone")

| Metric | Minimum |
|---|---|
| Effective single-class mAP50 | ≥ 0.75 |
| p95 inference latency (GPU) | < 30 ms |

---

## 6. Promotion Procedure

```
1. Run benchmark: python scripts/run_evaluation_benchmark.py --model candidate.pt --task weapon
2. Verify all promotion thresholds are met in benchmark output.
3. Copy candidate weights: cp candidate.pt models/weapon/current.pt
4. Update models/weapon/metadata.yaml — bump source_weight, training_summary.
5. Update models/registry.json if path or metadata location changed.
6. Commit: "promote weapon model vX — mAP50=0.XX, recall=0.XX"
7. Tag release: git tag model/weapon/vX
```

If any threshold is not met, the candidate **must not** replace `current.pt`. Open a tracking issue instead.

---

## 7. Model Lifecycle

```
COCO pretrained init
       │
       ▼
Fine-tuning on Aegis dataset (runs/aegis_{task}/{run_name}/weights/best.pt)
       │
       ▼
Benchmark evaluation (scripts/run_evaluation_benchmark.py)
       │
    pass? ──── NO ──→ iterate / retrain
       │ YES
       ▼
Promotion: copy to models/{task}/current.pt + update metadata.yaml + registry.json
       │
       ▼
Production inference (ModelRouter reads registry → loads current.pt)
```

---

## 8. Air-Gap Compliance

In air-gapped deployments (`inference.allow_weight_downloads: false` in `evaluation.local.yaml`), all weights must be present on disk before the system starts. `dependency_manager.py:validate_model_files_exist()` enforces this at boot and will raise `[CRITICAL FAILURE]` if any required weight is missing.
