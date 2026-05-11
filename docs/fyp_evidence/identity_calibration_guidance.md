# Identity calibration guidance

## Face threshold calibration

Script: `scripts/calibrate_identity_thresholds.py`

### Inputs

1. **Precomputed pairs** (`--pairs`): CSV / JSON / JSONL rows with `same` (boolean) and `similarity` (cosine similarity in \[0,1\]).
2. **Folder dataset** (`--dataset-root`): directories `person_001/`, `person_002/`, … each containing face images. The script builds genuine and impostor pairs from embeddings. If InsightFace is not available, the script exits with a clear error (no fabricated metrics).

### Outputs (per run directory)

Under `storage/identity_calibration/face_<timestamp>/`:

- `metrics.json` — FAR/FRR, TAR@FAR targets, threshold sweep metadata
- `threshold_sweep.csv`
- `report.md`

### Dataset layout (recommended)

```
datasets/identity_calibration/
  person_001/
    img1.jpg
    img2.jpg
  person_002/
    img1.jpg
```

At least two person folders with usable faces are required for cross-person impostor pairs.

## ReID benchmark

Script: `scripts/evaluate_reid_models.py`

### Layout A — images

```
datasets/reid_benchmark/
  query/
    person_001_cam1.jpg
  gallery/
    person_001_cam2.jpg
```

Identity IDs are parsed from filenames (prefix before `_cam` when present).

### Layout B — embeddings

`query.jsonl` and `gallery.jsonl` in the dataset root, each row containing `identity_id` and `embedding`.

### Outputs

`storage/identity_calibration/reid_<timestamp>/`:

- `metrics.json`
- `cmc_curve.csv` (when metrics include CMC points)
- `report.md`

## Operational policy

- Scripts must exit cleanly when datasets are missing; they must not invent metrics.
- Production should not treat default YAML thresholds as “promoted” without a recorded calibration run that passes your governance checks.
