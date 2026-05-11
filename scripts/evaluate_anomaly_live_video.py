#!/usr/bin/env python3
"""
Live decoded-video anomaly evaluation.

Runs pretrained VideoMAE (and optional violence YOLO) on real decoded frames.
This path does not use offline benchmark label simulation or _offline_predict.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_increment(name: str, count: int = 1) -> None:
    try:
        from inference.monitoring.metrics import get_metrics

        get_metrics().increment(name, count)
    except Exception:
        pass
    try:
        from inference.metrics import metrics

        metrics.increment(name, count)
    except Exception:
        pass


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = list(data.get("videos") or [])
    out: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        p = row.get("path")
        if not p:
            continue
        out.append(
            {
                "path": ROOT / str(p),
                "label": row.get("label"),
                "source": row.get("source"),
            }
        )
    return out


def _collect_videos(videos_arg: Path, manifest: Path | None) -> list[dict[str, Any]]:
    if manifest and manifest.is_file():
        return _load_manifest(manifest)
    if videos_arg.is_dir():
        return [{"path": p, "label": None, "source": "directory"} for p in sorted(videos_arg.glob("*.mp4"))]
    if videos_arg.is_file():
        return [{"path": videos_arg, "label": None, "source": "file"}]
    return []


def _evaluate_one_video(
    *,
    video_path: Path,
    model_path: str,
    violence_model: str | None,
    device: str,
    max_frames: int,
) -> dict[str, Any]:
    import cv2
    from inference.anomaly.pretrained_adapter import PretrainedVideoAdapter
    from inference.anomaly.rule_engine import RuleEngine
    from inference.anomaly.schemas import AnomalyWindow
    from inference.anomaly.violence_adapter import ViolenceVisualAdapter

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    frames: list[Any] = []
    try:
        for _ in range(max_frames):
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frames.append(frame)
    finally:
        cap.release()

    if len(frames) < 2:
        raise RuntimeError("insufficient frames decoded for live inference")

    window = AnomalyWindow(
        camera_id="live_eval",
        frames=frames,
        detections=[],
        tracks=[],
    )
    t0 = time.perf_counter()
    adapter = PretrainedVideoAdapter(model_path=model_path, device=device)
    adapter.load()
    model_pred = adapter.predict_clip(frames, {"camera_id": "live_eval", "window_seconds": 5.0})

    violence_pred = None
    violence_health: dict[str, Any] = {"status": "skipped"}
    if violence_model:
        va = ViolenceVisualAdapter(model_path=violence_model, device=device, is_production=False)
        va.load()
        violence_health = va.health()
        step = max(1, len(frames) // 8)
        v_frames = [{"image": frames[i]} for i in range(0, len(frames), step)]
        vw = AnomalyWindow(camera_id="live_eval", frames=v_frames, detections=[], tracks=[])
        violence_pred = va.predict_window(vw)

    rules = RuleEngine().evaluate(window)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    def _dump_pred(p: Any) -> dict[str, Any] | None:
        if p is None:
            return None
        return {
            "anomaly_type": p.anomaly_type,
            "score": p.score,
            "severity": p.severity,
            "source": p.source,
            "confidence": p.confidence,
        }

    fused_like = {
        "rule_engine_count": len(rules),
        "model": _dump_pred(model_pred),
        "violence": _dump_pred(violence_pred),
        "adapter_health": adapter.health(),
        "violence_health": violence_health,
    }

    return {
        "video": str(video_path.relative_to(ROOT)) if video_path.is_relative_to(ROOT) else str(video_path),
        "frame_count_decoded": len(frames),
        "latency_ms": round(latency_ms, 2),
        "live_inference": fused_like,
        "provider_status": {
            "video_model_loaded": adapter.is_loaded(),
            "violence_requested": bool(violence_model),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live anomaly evaluation on decoded video.")
    parser.add_argument("--videos", type=Path, required=True, help="Video file, directory of .mp4, or base path with --manifest")
    parser.add_argument("--model-path", type=str, required=True, help="VideoMAE / anomaly adapter directory")
    parser.add_argument("--violence-model", type=str, default="", help="Optional YOLO violence weights .pt")
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None, help="Optional YAML manifest (see configs/evaluation/anomaly_live_video_manifest.yaml)")
    parser.add_argument("--max-frames", type=int, default=120)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    videos = _collect_videos(args.videos, args.manifest)
    if not videos:
        print("No videos found.", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    latencies: list[float] = []

    for spec in videos:
        path = Path(spec["path"])
        _metric_increment("anomaly_live_eval_runs_total")
        try:
            row = _evaluate_one_video(
                video_path=path,
                model_path=args.model_path,
                violence_model=args.violence_model or None,
                device=args.device,
                max_frames=args.max_frames,
            )
            row["label"] = spec.get("label")
            row["source_meta"] = spec.get("source")
            rows.append(row)
            latencies.append(float(row["latency_ms"]))
        except Exception as exc:
            _metric_increment("anomaly_live_eval_failures_total")
            failures.append({"video": str(path), "error": str(exc)})

    metrics_payload = {
        "generated_at": _now_iso(),
        "video_count": len(videos),
        "successful": len(rows),
        "failed": len(failures),
        "model_path": args.model_path,
        "violence_model": args.violence_model or None,
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "note": "Offline _offline_predict results are not live inference metrics.",
    }
    (args.output_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    (args.output_dir / "latency_profile.json").write_text(
        json.dumps({"per_video_latency_ms": {r["video"]: r["latency_ms"] for r in rows}}, indent=2),
        encoding="utf-8",
    )
    jsonl_path = args.output_dir / "per_video_predictions.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")

    report_lines = [
        "# Live Anomaly Video Evaluation",
        "",
        "## 1. Model paths",
        f"- Video adapter path: `{args.model_path}`",
        f"- Violence model: `{args.violence_model or 'not provided'}`",
        "",
        "## 2. Videos evaluated",
        *[f"- `{r['video']}`" for r in rows],
        *[f"- FAILED `{f['video']}`: {f['error']}" for f in failures],
        "",
        "## 3. Live inference results",
        "Decoded frames were passed through the pretrained VideoMAE adapter and optional violence adapter.",
        "Rule-engine outputs are included when track/detection metadata exists (typically sparse for file-only runs).",
        "",
        "## 4. Latency",
        f"- Mean latency (ms): {metrics_payload['mean_latency_ms']}",
        f"- Max latency (ms): {metrics_payload['max_latency_ms']}",
        "",
        "## 5. Failure cases",
        *([f"- {item}" for item in failures] if failures else ["- None"]),
        "",
        "## 6. Difference from offline benchmark",
        "The offline anomaly benchmark runner may call `_offline_predict` on pre-materialized records.",
        "**Offline `_offline_predict` results are not live inference metrics.**",
        "This script only reports scores produced from decoded pixels in this run.",
        "",
        "## 7. Limitations",
        "- Limited frame budget per file (`--max-frame`) caps cost; not full-file coverage.",
        "- No guarantee of representativeness; larger real-world evaluation is still required.",
        "- Violence and VideoMAE adapters may be unavailable if weights or dependencies are missing.",
        "",
    ]
    (args.output_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps({"status": "ok", "output_dir": str(args.output_dir), "metrics": metrics_payload}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
