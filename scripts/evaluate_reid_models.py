#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

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


def _identity_id_from_image_stem(stem: str) -> str:
    if "_cam" in stem:
        return stem.split("_cam", 1)[0]
    parts = stem.split("_")
    if len(parts) >= 2 and parts[0] == "person":
        return f"{parts[0]}_{parts[1]}"
    return stem


def load_image_reid_layout(dataset_root: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = Path(dataset_root)
    qdir = root / "query"
    gdir = root / "gallery"
    if not qdir.is_dir() or not gdir.is_dir():
        raise FileNotFoundError("reid image dataset requires query/ and gallery/ subdirectories")
    exts = {".jpg", ".jpeg", ".png", ".webp"}

    def _scan(folder: Path) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in exts:
                continue
            rows.append({"identity_id": _identity_id_from_image_stem(path.stem), "image_path": str(path.resolve())})
        return rows

    query = _scan(qdir)
    gallery = _scan(gdir)
    if not query or not gallery:
        raise ValueError("query/ or gallery/ folder is empty")
    return query, gallery


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
    lines = [
        "# ReID benchmark report",
        "",
        "Rank-1 / Rank-5 / mAP are computed from real embeddings only.",
        "This does **not** confirm identity.",
        "",
        f"- Rank-1: {metrics.get('rank_1')}",
        f"- Rank-5: {metrics.get('rank_5')}",
        f"- mAP: {metrics.get('map')}",
        f"- Overlap / leakage warning: {metrics.get('overlap_or_leakage_detected')}",
        f"- Warnings: {metrics.get('warnings')}",
        "",
        "Requires operator review for any live identity decision.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        default=None,
        help="Directory with query/ + gallery/ images, or query.jsonl + gallery.jsonl embeddings.",
    )
    parser.add_argument("--query-file", default=None, help="Optional query embedding file.")
    parser.add_argument("--gallery-file", default=None, help="Optional gallery embedding file.")
    parser.add_argument("--device", default="cpu", help="Torch device for OSNet extraction (e.g. cpu or cuda:0).")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: storage/identity_calibration/reid_<timestamp>).",
    )
    args = parser.parse_args()

    query_records: list[dict[str, Any]]
    gallery_records: list[dict[str, Any]]

    if args.query_file and args.gallery_file:
        query_records = load_embedding_records(args.query_file)
        gallery_records = load_embedding_records(args.gallery_file)
    elif args.dataset_root:
        root = Path(args.dataset_root)
        if not root.exists():
            print("dataset missing: --dataset-root path does not exist", file=sys.stderr)
            print(
                "Expected layout:\n"
                "  datasets/reid_benchmark/\n"
                "    query/person_001_cam1.jpg\n"
                "    gallery/person_001_cam2.jpg\n"
                "or embedding files query.jsonl + gallery.jsonl in the same folder.",
                file=sys.stderr,
            )
            sys.exit(2)
        qjson = root / "query.jsonl"
        gjson = root / "gallery.jsonl"
        if qjson.exists() and gjson.exists():
            try:
                query_records, gallery_records = load_query_gallery_layout(root)
            except ValueError as exc:
                print(f"dataset missing: {exc}", file=sys.stderr)
                sys.exit(2)
        elif (root / "query").is_dir() and (root / "gallery").is_dir():
            try:
                query_records, gallery_records = load_image_reid_layout(root)
            except (FileNotFoundError, ValueError) as exc:
                print(f"dataset missing: {exc}", file=sys.stderr)
                sys.exit(2)
            try:
                adapter = OSNetReIDAdapter(device=str(args.device))
                query_records = adapter.extract(query_records)
                gallery_records = adapter.extract(gallery_records)
            except Exception as exc:
                print(f"ReID runtime unavailable: {exc}", file=sys.stderr)
                sys.exit(4)
        else:
            print(
                "dataset missing: expected query.jsonl + gallery.jsonl or query/ + gallery/ image folders",
                file=sys.stderr,
            )
            sys.exit(2)
    else:
        print("dataset missing: provide --dataset-root or both --query-file and --gallery-file", file=sys.stderr)
        sys.exit(2)

    metrics = evaluate_reid(query_records, gallery_records)
    out_dir = Path(args.output_dir) if args.output_dir else Path("storage") / "identity_calibration" / f"reid_{_now_stamp()}"
    out_path = write_reid_outputs(metrics, out_dir)
    print(json.dumps({"status": "ok", "output_dir": str(out_path), "rank_1": metrics.get("rank_1")}, indent=2))


if __name__ == "__main__":
    main()
