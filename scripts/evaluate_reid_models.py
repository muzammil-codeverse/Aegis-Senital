#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.evaluation.metrics.reid_metrics import compute_reid_metrics


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_embedding(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            return [float(v) for v in json.loads(text)]
    raise ValueError("Embedding value must be a list or JSON array string.")


def load_embedding_records(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if file_path.suffix.lower() == ".jsonl":
        items = []
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["embedding"] = _parse_embedding(row["embedding"])
            items.append(row)
        return items
    if file_path.suffix.lower() == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("JSON embedding file must contain a list.")
        for row in payload:
            row["embedding"] = _parse_embedding(row["embedding"])
        return payload
    if file_path.suffix.lower() == ".csv":
        rows = []
        with file_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                row["embedding"] = _parse_embedding(row["embedding"])
                rows.append(row)
        return rows
    raise ValueError(f"Unsupported embedding file format: {file_path.suffix}")


def load_query_gallery_layout(dataset_root: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = Path(dataset_root)
    query_file = root / "query.jsonl"
    gallery_file = root / "gallery.jsonl"
    if query_file.exists() and gallery_file.exists():
        return load_embedding_records(query_file), load_embedding_records(gallery_file)
    raise ValueError("Expected query.jsonl and gallery.jsonl under dataset root for lightweight evaluation.")


@dataclass
class BaseReIDAdapter:
    name: str

    def extract(self, _records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError


class OSNetReIDAdapter(BaseReIDAdapter):
    def __init__(self, device: str = "cpu") -> None:
        super().__init__(name="osnet")
        self.device = device

    def extract(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from torchreid.reid.utils import FeatureExtractor
        import cv2
        import numpy as np

        extractor = FeatureExtractor(model_name="osnet_x1_0", device=self.device)
        outputs = []
        for row in records:
            image_path = row.get("image_path")
            if not image_path:
                continue
            image = cv2.imread(str(image_path))
            if image is None:
                outputs.append({**row, "embedding": []})
                continue
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            embedding = extractor([rgb]).cpu().numpy().reshape(-1).astype(np.float32).tolist()
            outputs.append({**row, "embedding": embedding})
        return outputs


class FastReIDAdapter(BaseReIDAdapter):
    def __init__(self) -> None:
        super().__init__(name="fastreid")

    def extract(self, _records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError("FastReID adapter placeholder only.")


class TransReIDAdapter(BaseReIDAdapter):
    def __init__(self) -> None:
        super().__init__(name="transreid")

    def extract(self, _records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError("TransReID adapter placeholder only.")


class ClipReIDAdapter(BaseReIDAdapter):
    def __init__(self) -> None:
        super().__init__(name="clip-reid")

    def extract(self, _records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError("CLIP-ReID adapter placeholder only.")


def evaluate_reid(query_records: list[dict[str, Any]], gallery_records: list[dict[str, Any]]) -> dict[str, Any]:
    metric_result = compute_reid_metrics(query_records, gallery_records)
    return metric_result.to_dict()


def write_reid_outputs(metrics: dict[str, Any], output_dir: str | Path) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    cmc_curve = metrics.get("cmc_curve", [])
    if cmc_curve:
        with (out_dir / "cmc_curve.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(cmc_curve[0].keys()))
            writer.writeheader()
            writer.writerows(cmc_curve)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", default=None, help="Directory containing query.jsonl and gallery.jsonl.")
    parser.add_argument("--query-file", default=None, help="Optional query embedding file.")
    parser.add_argument("--gallery-file", default=None, help="Optional gallery embedding file.")
    parser.add_argument(
        "--output-dir",
        default=str(Path("storage") / "evaluation_runs" / f"reid_eval_{_now_stamp()}"),
        help="Output directory for evaluation artifacts.",
    )
    args = parser.parse_args()

    if args.query_file and args.gallery_file:
        query_records = load_embedding_records(args.query_file)
        gallery_records = load_embedding_records(args.gallery_file)
    elif args.dataset_root:
        query_records, gallery_records = load_query_gallery_layout(args.dataset_root)
    else:
        raise SystemExit("Provide either --dataset-root or both --query-file and --gallery-file.")

    metrics = evaluate_reid(query_records, gallery_records)
    out_dir = write_reid_outputs(metrics, args.output_dir)
    print(json.dumps({"status": "ok", "output_dir": str(out_dir), "rank_1": metrics.get("rank_1")}, indent=2))


if __name__ == "__main__":
    main()
