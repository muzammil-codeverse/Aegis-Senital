#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.env_loader import load_project_env


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_candidate_videos(root: Path) -> list[Path]:
    candidates: list[Path] = []
    patterns = (
        "datasets/test_videos/**/*.mp4",
        "storage/uploaded_videos/**/*.mp4",
        "storage/replay/**/*.mp4",
    )
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in candidates:
                candidates.append(path)
    return candidates[:5]


def _latest_anomaly_benchmark(root: Path) -> tuple[Path | None, dict[str, Any]]:
    benchmark_dir = root / "storage" / "evaluation_runs" / "anomaly"
    if not benchmark_dir.exists():
        return None, {}
    for candidate in sorted(benchmark_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return candidate, payload
    return None, {}


def _latest_live_eval_output(out_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    raw_dir = out_dir / "raw"
    if not raw_dir.exists():
        return None, {}
    for candidate in sorted(raw_dir.glob("run_*"), key=lambda item: item.stat().st_mtime, reverse=True):
        metrics_path = candidate / "metrics.json"
        if not metrics_path.exists():
            continue
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return candidate, payload
    return None, {}


def _run_live_eval(*, root: Path, videos: list[Path], out_dir: Path, device: str) -> tuple[Path | None, dict[str, Any], str | None]:
    if not videos:
        return None, {}, "No candidate videos were found."
    model_path = root / "models" / "anomaly" / "current"
    if not model_path.exists():
        return None, {}, f"Anomaly model path missing: {model_path}"

    live_run_dir = out_dir / "raw" / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    live_run_dir.mkdir(parents=True, exist_ok=True)
    video_arg = videos[0]
    violence_model = root / "models" / "anomaly" / "violence_yolo11.pt"
    command = [
        sys.executable,
        str(root / "scripts" / "evaluate_anomaly_live_video.py"),
        "--videos",
        str(video_arg),
        "--model-path",
        str(model_path),
        "--device",
        device,
        "--output-dir",
        str(live_run_dir),
        "--max-frames",
        "120",
    ]
    if violence_model.exists():
        command.extend(["--violence-model", str(violence_model)])

    result = subprocess.run(command, capture_output=True, text=True, cwd=root)
    metrics_path = live_run_dir / "metrics.json"
    if result.returncode != 0 or not metrics_path.exists():
        stderr = (result.stderr or result.stdout or "").strip()
        return None, {}, stderr or "Live anomaly evaluation failed."
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    return live_run_dir, payload if isinstance(payload, dict) else {}, None


def build_live_eval_summary(*, root: Path, device: str, generate_if_missing: bool = True) -> dict[str, Any]:
    out_dir = root / "storage" / "anomaly_live_eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    offline_path, offline_payload = _latest_anomaly_benchmark(root)
    live_path, live_payload = _latest_live_eval_output(out_dir)
    limitations: list[str] = []
    generation_notes: list[str] = []
    candidate_videos = _find_candidate_videos(root)

    if not live_payload and generate_if_missing:
        live_path, live_payload, generation_error = _run_live_eval(
            root=root,
            videos=candidate_videos,
            out_dir=out_dir,
            device=device,
        )
        if generation_error:
            generation_notes.append(generation_error)

    insufficient = not bool(live_payload)
    if insufficient:
        limitations.append("Live anomaly evaluation evidence is limited by available local videos and model/runtime readiness.")
    if candidate_videos:
        generation_notes.append(f"Candidate videos inspected: {len(candidate_videos)}")
    else:
        generation_notes.append("No local candidate videos were available for a fresh live run.")

    live_metrics = {
        "source": str(live_path.relative_to(root)) if live_path else None,
        "video_count": int(live_payload.get("video_count") or 0),
        "successful": int(live_payload.get("successful") or 0),
        "failed": int(live_payload.get("failed") or 0),
        "mean_latency_ms": float(live_payload.get("mean_latency_ms") or 0.0),
        "max_latency_ms": float(live_payload.get("max_latency_ms") or 0.0),
        "model_path": live_payload.get("model_path"),
        "violence_model": live_payload.get("violence_model"),
    }
    offline_metrics = {
        "source": str(offline_path.relative_to(root)) if offline_path else None,
        "metrics": dict(offline_payload.get("metrics") or offline_payload or {}),
    }

    summary = {
        "generated_at": _now_iso(),
        "device": device,
        "status": "insufficient_data" if insufficient else "ok",
        "insufficient_data_but_evidence_file_present": insufficient,
        "live_eval": live_metrics,
        "offline_benchmark": offline_metrics,
        "candidate_videos": [
            str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            for path in candidate_videos
        ],
        "limitations": limitations,
        "generation_notes": generation_notes,
    }
    return summary


def write_live_eval_artifacts(*, root: Path, summary: dict[str, Any]) -> tuple[Path, Path]:
    out_dir = root / "storage" / "anomaly_live_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "live_eval_summary.json"
    report_path = out_dir / "live_eval_report.md"

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    report_lines = [
        "# Anomaly Live Evaluation Summary",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Status: `{summary['status']}`",
        f"- Evidence file present despite insufficient data: `{summary['insufficient_data_but_evidence_file_present']}`",
        f"- Device requested: `{summary['device']}`",
        "",
        "## Live Evaluation",
        f"- Source: `{summary['live_eval'].get('source') or 'not generated'}`",
        f"- Videos considered: `{summary['live_eval'].get('video_count', 0)}`",
        f"- Successful: `{summary['live_eval'].get('successful', 0)}`",
        f"- Failed: `{summary['live_eval'].get('failed', 0)}`",
        f"- Mean latency (ms): `{summary['live_eval'].get('mean_latency_ms', 0.0)}`",
        f"- Max latency (ms): `{summary['live_eval'].get('max_latency_ms', 0.0)}`",
        "",
        "## Offline Benchmark Reference",
        f"- Source: `{summary['offline_benchmark'].get('source') or 'not found'}`",
        "",
        "## Limitations",
    ]
    if summary["limitations"]:
        report_lines.extend(f"- {item}" for item in summary["limitations"])
    else:
        report_lines.append("- No additional limitations were recorded.")
    report_lines.extend(
        [
            "",
            "## Generation Notes",
            *[f"- {item}" for item in summary["generation_notes"]],
        ]
    )
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return summary_path, report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate anomaly live-eval governance evidence.")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--check-only", action="store_true", help="Only summarize existing evidence; do not trigger a fresh live run.")
    args = parser.parse_args()

    load_project_env()
    summary = build_live_eval_summary(root=ROOT, device=str(args.device), generate_if_missing=not args.check_only)
    summary_path, report_path = write_live_eval_artifacts(root=ROOT, summary=summary)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary_path": str(summary_path),
                "report_path": str(report_path),
                "insufficient_data_but_evidence_file_present": summary["insufficient_data_but_evidence_file_present"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
