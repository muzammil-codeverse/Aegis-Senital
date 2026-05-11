#!/usr/bin/env python3
"""Face identity threshold calibration from pair scores or a labeled folder dataset.

Does not fabricate metrics. Requires real pair inputs or a dataset with extractable embeddings.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.app.evaluation.metrics.face_metrics import compute_face_metrics

ACCEPTANCE_POLICY = {
    "max_far_at_operating_threshold": 0.01,
    "max_frr_at_operating_threshold": 0.10,
    "min_tar_at_far_1e_2": 0.85,
}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _print_dataset_layout() -> None:
    print(
        "Expected dataset layout under --dataset-root:\n"
        "  datasets/identity_calibration/\n"
        "    person_001/\n"
        "      img1.jpg\n"
        "      img2.jpg\n"
        "    person_002/\n"
        "      img1.jpg\n"
        "Same-person pairs are generated within each person folder; impostor pairs across folders."
    )


def load_pair_results(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if file_path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if file_path.suffix.lower() == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        raise ValueError("JSON input must be a list of pair result objects.")
    if file_path.suffix.lower() == ".csv":
        rows = []
        with file_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(
                    {
                        "same": str(row.get("same", "")).lower() in {"1", "true", "yes"},
                        "similarity": float(row.get("similarity", row.get("score", 0.0)) or 0.0),
                    }
                )
        return rows
    raise ValueError(f"Unsupported pair-results format: {file_path.suffix}")


def _discover_person_dirs(root: Path) -> list[tuple[str, list[Path]]]:
    people: list[tuple[str, list[Path]]] = []
    if not root.is_dir():
        return people
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if not re.match(r"^person_", child.name):
            continue
        images = sorted(
            p for p in child.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if images:
            people.append((child.name, images))
    return people


def _build_pairs_from_images(
    people: list[tuple[str, list[Path]]],
    *,
    min_quality_score: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return pair_results using InsightFace embeddings; never invents similarity scores."""
    try:
        from insightface.app import FaceAnalysis
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "Face embedding stack unavailable (InsightFace import failed). "
            "Install runtime dependencies or use --pairs with precomputed scores.\n"
            f"Detail: {exc}"
        ) from exc

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))

    def _embedding(image_path: Path) -> tuple[list[float] | None, float | None]:
        import cv2

        bgr = cv2.imread(str(image_path))
        if bgr is None:
            return None, None
        faces = app.get(bgr)
        if not faces:
            return None, None
        face = max(faces, key=lambda f: float(getattr(f, "det_score", 0.0) or 0.0))
        qual = float(getattr(face, "det_score", 0.0) or 0.0)
        if qual < min_quality_score:
            return None, qual
        emb = getattr(face, "embedding", None)
        if emb is None:
            return None, qual
        vec = np.array(emb, dtype=np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        return vec.tolist(), qual

    embeddings: dict[str, list[tuple[Path, list[float], float]]] = {}
    rejected_low_quality = 0
    for person, paths in people:
        embeddings[person] = []
        for p in paths:
            emb, qual = _embedding(p)
            if emb is None:
                if qual is not None and qual < min_quality_score:
                    rejected_low_quality += 1
                continue
            embeddings[person].append((p, emb, float(qual or 0.0)))

    pair_results: list[dict[str, Any]] = []
    for pid, items in embeddings.items():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a = items[i][1]
                b = items[j][1]
                sim = sum(x * y for x, y in zip(a, b))
                pair_results.append({"same": True, "similarity": float(sim), "person": pid})
    persons = list(embeddings.keys())
    for p1 in persons:
        for p2 in persons:
            if p1 >= p2:
                continue
            for _path_a, emb_a, _ in embeddings[p1]:
                for _path_b, emb_b, _ in embeddings[p2]:
                    sim = sum(x * y for x, y in zip(emb_a, emb_b))
                    pair_results.append({"same": False, "similarity": float(sim), "person_a": p1, "person_b": p2})
                    break
                break

    meta = {
        "person_count": len(persons),
        "pair_count": len(pair_results),
        "low_quality_face_rejected": rejected_low_quality,
    }
    return pair_results, meta


def build_distance_histogram(pair_results: list[dict[str, Any]], bins: int = 20) -> dict[str, list[dict[str, Any]]]:
    same_scores = [1.0 - float(row["similarity"]) for row in pair_results if row.get("same")]
    diff_scores = [1.0 - float(row["similarity"]) for row in pair_results if not row.get("same")]

    def _hist(values: list[float]) -> list[dict[str, Any]]:
        if not values:
            return []
        low, high = min(values), max(values)
        if low == high:
            return [{"bin_start": round(low, 4), "bin_end": round(high, 4), "count": len(values)}]
        width = (high - low) / bins
        hist = []
        for index in range(bins):
            start = low + index * width
            end = high if index == bins - 1 else start + width
            if index == bins - 1:
                count = sum(1 for value in values if start <= value <= end)
            else:
                count = sum(1 for value in values if start <= value < end)
            hist.append({"bin_start": round(start, 4), "bin_end": round(end, 4), "count": count})
        return hist

    return {
        "same_person": _hist(same_scores),
        "different_person": _hist(diff_scores),
    }


def calibrate_thresholds(pair_results: list[dict[str, Any]], far_levels: list[float] | None = None) -> dict[str, Any]:
    if far_levels is None:
        far_levels = [0.1, 0.01, 0.001]
    metric_result = compute_face_metrics(pair_results, far_thresholds=far_levels)
    tar_map = metric_result.tar_at_far_thresholds or {}
    tar_key = "FAR=1e-02"
    if tar_key not in tar_map:
        tar_key = next(iter(tar_map), "")
    tar_at_far = float(tar_map.get(tar_key, 0.0)) if tar_key else 0.0
    accepted = (
        metric_result.far is not None
        and metric_result.frr is not None
        and metric_result.far <= ACCEPTANCE_POLICY["max_far_at_operating_threshold"]
        and metric_result.frr <= ACCEPTANCE_POLICY["max_frr_at_operating_threshold"]
        and tar_at_far >= ACCEPTANCE_POLICY["min_tar_at_far_1e_2"]
    )
    return {
        "metrics": metric_result.to_dict(),
        "distance_histogram": build_distance_histogram(pair_results),
        "acceptance_policy": ACCEPTANCE_POLICY,
        "threshold_accepted": bool(accepted),
    }


def write_calibration_outputs(result: dict[str, Any], output_dir: str | Path) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    sweep = result["metrics"].get("threshold_sweep", [])
    if sweep:
        with (out_dir / "threshold_sweep.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(sweep[0].keys()))
            writer.writeheader()
            writer.writerows(sweep)

    roc_curve = result["metrics"].get("roc_curve_points", [])
    if roc_curve:
        with (out_dir / "roc_curve.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(roc_curve[0].keys()))
            writer.writeheader()
            writer.writerows(roc_curve)

    report = out_dir / "report.md"
    metrics = result["metrics"]
    report.write_text(
        "\n".join(
            [
                "# Face identity calibration report",
                "",
                "This report summarizes operator-controlled calibration metrics only.",
                "It does **not** confirm identity.",
                "",
                f"- FAR (operating point): {metrics.get('far')}",
                f"- FRR (operating point): {metrics.get('frr')}",
                f"- TAR@FAR targets: {metrics.get('tar_at_far_thresholds')}",
                f"- Recommended threshold (dataset fit only): {metrics.get('recommended_threshold')}",
                f"- Policy threshold accepted: {result.get('threshold_accepted')}",
                "",
                "Low-quality face images must be rejected upstream; validate on held-out data before production.",
                "",
                "Requires operator review for any live identity decision.",
            ]
        ),
        encoding="utf-8",
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default=None, help="JSON/JSONL/CSV pair results with same + similarity.")
    parser.add_argument("--dataset-root", default=None, help="Folder with person_*/images per calibration layout.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: storage/identity_calibration/face_<timestamp>).",
    )
    parser.add_argument("--min-quality-score", type=float, default=0.65)
    parser.add_argument(
        "--far-levels",
        default="0.1,0.01,0.001",
        help="Comma-separated FAR targets for TAR@FAR reporting.",
    )
    args = parser.parse_args()

    far_levels = [float(x.strip()) for x in str(args.far_levels).split(",") if x.strip()]

    pair_results: list[dict[str, Any]] | None = None
    dataset_meta: dict[str, Any] = {}

    if args.pairs:
        pair_results = load_pair_results(args.pairs)
    elif args.dataset_root:
        root = Path(args.dataset_root)
        if not root.exists():
            print("dataset missing: --dataset-root path does not exist", file=sys.stderr)
            _print_dataset_layout()
            sys.exit(2)
        people = _discover_person_dirs(root)
        if len(people) < 2:
            print("dataset missing: need at least two person_* folders with images", file=sys.stderr)
            _print_dataset_layout()
            sys.exit(2)
        pair_results, dataset_meta = _build_pairs_from_images(people, min_quality_score=float(args.min_quality_score))
        if not pair_results:
            print("dataset missing: no usable face pairs after quality filtering", file=sys.stderr)
            sys.exit(3)
    else:
        print("dataset missing: provide --pairs or --dataset-root", file=sys.stderr)
        _print_dataset_layout()
        sys.exit(2)

    result = calibrate_thresholds(pair_results, far_levels=far_levels)
    if dataset_meta:
        result["dataset"] = dataset_meta

    out_dir = Path(args.output_dir) if args.output_dir else Path("storage") / "identity_calibration" / f"face_{_now_stamp()}"
    out_path = write_calibration_outputs(result, out_dir)
    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_path),
                "threshold_accepted": result["threshold_accepted"],
                "recommended_threshold": result["metrics"].get("recommended_threshold"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
