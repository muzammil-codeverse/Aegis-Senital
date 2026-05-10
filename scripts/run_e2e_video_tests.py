#!/usr/bin/env python3
"""End-to-end video pipeline test for Aegis Sentinel.

Reads each video from the manifest, runs frames through every active ML
subsystem, and writes a structured JSON + Markdown report.

Usage:
  python scripts/run_e2e_video_tests.py \
    --manifest datasets/test_videos/manifest.json \
    --output-dir storage/test_outputs \
    --device cuda \
    --max-frames 300
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SubsystemResult:
    name: str
    loaded: bool = False
    frames_processed: int = 0
    detections_total: int = 0
    errors: list[str] = field(default_factory=list)
    latency_ms_avg: float = 0.0
    notes: str = ""


@dataclass
class VideoTestResult:
    video_id: str
    file_path: str
    source: str
    query: str
    expected_detections: list[str]
    frames_sampled: int = 0
    duration_s: float = 0.0
    fps: float = 0.0
    subsystems: dict[str, dict] = field(default_factory=dict)
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Model loaders
# ---------------------------------------------------------------------------

def _load_yolo_model(path: str, device: str):
    from ultralytics import YOLO
    m = YOLO(path)
    return m


def _load_sam2(device: str):
    from inference.segmentation.segmentation_service import SegmentationService
    svc = SegmentationService()
    if not svc.is_loaded():
        try:
            svc.load()
        except Exception as exc:
            return svc, str(exc)
    return svc, None


def _load_insightface(device: str):
    from insightface.app import FaceAnalysis
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "cuda" else ["CPUExecutionProvider"]
    app = FaceAnalysis(name="buffalo_l", root=str(ROOT / "models"), providers=providers)
    app.prepare(ctx_id=0 if device == "cuda" else -1, det_size=(640, 640))
    return app


def _load_anomaly_service():
    from inference.anomaly.anomaly_service import AnomalyService
    svc = AnomalyService(is_production=False)
    return svc


# ---------------------------------------------------------------------------
# Frame-level inference helpers
# ---------------------------------------------------------------------------

def _run_yolo(model, frame, conf_thresh: float = 0.25) -> list[dict]:
    results = model(frame, conf=conf_thresh, verbose=False)
    detections = []
    if results:
        r = results[0]
        if r.boxes is not None:
            for box in r.boxes:
                detections.append({
                    "class_name": model.names[int(box.cls[0])],
                    "confidence": float(box.conf[0]),
                    "bbox": [float(v) for v in box.xyxy[0].tolist()],
                    "source_model": "yolo",
                })
    return detections


def _run_segmentation(svc, frame, detections: list[dict]) -> dict:
    if not svc.is_loaded() or not detections:
        return {"status": "skipped", "mask_count": 0}
    payload = svc.refine(image=frame, detections=detections)
    return {"status": payload.get("status"), "mask_count": payload.get("mask_count", 0)}


def _run_identity(face_app, frame) -> dict:
    import numpy as np
    arr = frame if isinstance(frame, np.ndarray) else np.array(frame)
    try:
        faces = face_app.get(arr)
        return {"faces_detected": len(faces), "crashed": False}
    except Exception as exc:
        return {"faces_detected": 0, "crashed": True, "error": str(exc)[:80]}


def _run_anomaly(svc, frame_id: int, timestamp: float, detections: list[dict], tracks: list[dict]) -> dict:
    try:
        preds = svc.add_frame(
            camera_id="test_cam",
            frame_id=frame_id,
            timestamp=timestamp,
            detections=detections,
            tracks=tracks,
        )
        preds = preds or []
        return {
            "predictions": len(preds),
            "max_score": max(
                (p.score if hasattr(p, "score") else p.get("score", 0) for p in preds), default=0.0
            ),
            "crashed": False,
        }
    except Exception as exc:
        return {"predictions": 0, "max_score": 0.0, "crashed": True, "error": str(exc)[:120]}


def _run_rule_engine(svc, frame, tracks: list[dict], timestamp: float) -> dict:
    try:
        from inference.anomaly.rule_engine import RuleEngine
        from inference.anomaly.temporal_buffer import TemporalBuffer
        buf = TemporalBuffer(window_seconds=5, sample_rate=5)
        buf.add(timestamp=timestamp, tracks=tracks)
        windows = buf.get_windows()
        if not windows:
            return {"events": 0, "crashed": False}
        engine = RuleEngine()
        events = engine.evaluate(windows[-1])
        return {"events": len(events), "crashed": False}
    except Exception as exc:
        return {"events": 0, "crashed": True, "error": str(exc)[:120]}


# ---------------------------------------------------------------------------
# Video test runner
# ---------------------------------------------------------------------------

def _test_video(
    entry: dict,
    models: dict[str, Any],
    max_frames: int,
    device: str,
) -> VideoTestResult:
    import cv2
    import numpy as np

    result = VideoTestResult(
        video_id=entry["video_id"],
        file_path=entry["file_path"],
        source=entry.get("source", "unknown"),
        query=entry.get("query", ""),
        expected_detections=entry.get("expected_detections", []),
    )

    video_path = ROOT / entry["file_path"]
    if not video_path.exists():
        result.failures.append(f"Video file missing: {video_path}")
        return result

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        result.failures.append(f"Cannot open video: {video_path}")
        return result

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    result.fps = round(fps, 2)
    result.duration_s = round(total_frames / fps, 2)

    # Sample evenly up to max_frames
    sample_indices = set(
        int(i * total_frames / min(max_frames, total_frames))
        for i in range(min(max_frames, total_frames))
    )
    sample_indices = sorted(sample_indices)

    # Per-subsystem accumulators
    phone_dets, weapon_dets, violence_dets = 0, 0, 0
    phone_latencies, weapon_latencies, violence_latencies = [], [], []
    seg_masks, seg_latencies = 0, []
    face_results = []
    anomaly_preds_total = 0
    rule_events = []
    errors: dict[str, list[str]] = {k: [] for k in ("phone", "weapon", "violence", "segmentation", "identity", "anomaly", "rule_engine")}
    anomaly_svc = None
    if "anomaly" in models:
        anomaly_svc = models["anomaly"]

    sampled_count = 0
    frame_idx = 0
    current_sample_idx = 0

    while current_sample_idx < len(sample_indices):
        target = sample_indices[current_sample_idx]
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ret, frame = cap.read()
        if not ret:
            break
        current_sample_idx += 1
        sampled_count += 1
        timestamp = target / fps

        all_detections: list[dict] = []

        # Phone detection
        if "phone" in models:
            t0 = time.monotonic()
            try:
                dets = _run_yolo(models["phone"], frame)
                phone_dets += len(dets)
                all_detections.extend(dets)
            except Exception as exc:
                errors["phone"].append(str(exc)[:80])
            phone_latencies.append((time.monotonic() - t0) * 1000)

        # Weapon detection
        if "weapon" in models:
            t0 = time.monotonic()
            try:
                dets = _run_yolo(models["weapon"], frame)
                weapon_dets += len(dets)
                all_detections.extend(dets)
            except Exception as exc:
                errors["weapon"].append(str(exc)[:80])
            weapon_latencies.append((time.monotonic() - t0) * 1000)

        # Violence detection
        if "violence" in models:
            t0 = time.monotonic()
            try:
                dets = _run_yolo(models["violence"], frame)
                violence_dets += len(dets)
                all_detections.extend(dets)
            except Exception as exc:
                errors["violence"].append(str(exc)[:80])
            violence_latencies.append((time.monotonic() - t0) * 1000)

        # Segmentation (run on first 10 frames with detections)
        if "segmentation" in models and sampled_count <= 10 and all_detections:
            t0 = time.monotonic()
            try:
                seg_out = _run_segmentation(models["segmentation"], frame, all_detections)
                seg_masks += seg_out.get("mask_count", 0)
            except Exception as exc:
                errors["segmentation"].append(str(exc)[:80])
            seg_latencies.append((time.monotonic() - t0) * 1000)

        # Identity (face) — run on every 5th sampled frame
        if "identity" in models and sampled_count % 5 == 0:
            try:
                face_out = _run_identity(models["identity"], frame)
                face_results.append(face_out)
                if face_out.get("crashed"):
                    errors["identity"].append(face_out.get("error", "crashed"))
            except Exception as exc:
                errors["identity"].append(str(exc)[:80])

        # Anomaly + rule engine — every 5th sampled frame
        if sampled_count % 5 == 0:
            tracks = [
                {
                    "track_id": f"t{i}",
                    "class_name": d["class_name"],
                    "bbox": d["bbox"],
                    "confidence": d["confidence"],
                    "velocity": [0.0, 0.0],
                    "speed": 0.0,
                }
                for i, d in enumerate(all_detections)
            ]
            # AnomalyService
            if anomaly_svc is not None:
                try:
                    a_out = _run_anomaly(anomaly_svc, sampled_count, timestamp, all_detections, tracks)
                    anomaly_preds_total += a_out.get("predictions", 0)
                    if a_out.get("crashed"):
                        errors["anomaly"].append(a_out.get("error", "crashed"))
                except Exception as exc:
                    errors["anomaly"].append(str(exc)[:80])
            # Rule engine (standalone smoke)
            try:
                rule_out = _run_rule_engine(None, frame, tracks, timestamp)
                rule_events.append(rule_out.get("events", 0))
                if rule_out.get("crashed"):
                    errors["rule_engine"].append(rule_out.get("error", "crashed"))
            except Exception as exc:
                errors["rule_engine"].append(str(exc)[:80])

    cap.release()
    result.frames_sampled = sampled_count

    def _avg(lst): return round(sum(lst) / len(lst), 2) if lst else 0.0

    result.subsystems = {
        "phone_detector": {
            "loaded": "phone" in models,
            "frames_processed": len(phone_latencies),
            "detections_total": phone_dets,
            "latency_ms_avg": _avg(phone_latencies),
            "errors": errors["phone"],
        },
        "weapon_detector": {
            "loaded": "weapon" in models,
            "frames_processed": len(weapon_latencies),
            "detections_total": weapon_dets,
            "latency_ms_avg": _avg(weapon_latencies),
            "errors": errors["weapon"],
        },
        "violence_detector": {
            "loaded": "violence" in models,
            "frames_processed": len(violence_latencies),
            "detections_total": violence_dets,
            "latency_ms_avg": _avg(violence_latencies),
            "errors": errors["violence"],
        },
        "segmentation": {
            "loaded": "segmentation" in models and models.get("segmentation") is not None,
            "frames_processed": len(seg_latencies),
            "masks_generated": seg_masks,
            "latency_ms_avg": _avg(seg_latencies),
            "errors": errors["segmentation"],
        },
        "identity_face": {
            "loaded": "identity" in models,
            "frames_checked": len(face_results),
            "total_faces_detected": sum(r.get("faces_detected", 0) for r in face_results),
            "crashes": sum(1 for r in face_results if r.get("crashed")),
            "errors": errors["identity"],
        },
        "anomaly_service": {
            "loaded": anomaly_svc is not None,
            "frames_evaluated": len(rule_events),
            "total_predictions": anomaly_preds_total,
            "errors": errors["anomaly"],
        },
        "rule_engine": {
            "loaded": True,
            "frames_evaluated": len(rule_events),
            "total_events_generated": sum(rule_events),
            "errors": errors["rule_engine"],
        },
    }

    # Determine pass/fail
    blocker_errors = []
    for subsystem, data in result.subsystems.items():
        if data.get("errors") and subsystem in ("phone_detector", "weapon_detector", "violence_detector"):
            blocker_errors.append(f"{subsystem}: {data['errors'][0]}")
        if data.get("crashes", 0) > 0:
            blocker_errors.append(f"{subsystem}: crashed on face input")

    result.failures = blocker_errors
    result.passed = len(blocker_errors) == 0
    return result


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def _write_json_report(results: list[VideoTestResult], output_dir: Path) -> Path:
    report = {
        "generated_at": time.time(),
        "total_videos": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "videos": [asdict(r) for r in results],
    }
    path = output_dir / "e2e_video_test_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_markdown_report(results: list[VideoTestResult], output_dir: Path) -> Path:
    lines = ["# Aegis Sentinel — E2E Video Test Report", ""]
    lines.append(f"**Total videos tested:** {len(results)}")
    lines.append(f"**Passed:** {sum(1 for r in results if r.passed)}")
    lines.append(f"**Failed:** {sum(1 for r in results if not r.passed)}")
    lines.append("")

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"## [{status}] {r.video_id} — {r.query}")
        lines.append(f"- Source: {r.source} | Duration: {r.duration_s}s @ {r.fps}fps | Frames sampled: {r.frames_sampled}")
        lines.append(f"- Expected detections: {r.expected_detections}")
        if r.failures:
            lines.append(f"- **Failures:** {'; '.join(r.failures)}")
        lines.append("")
        lines.append("| Subsystem | Loaded | Frames | Detections/Masks | Avg Latency | Errors |")
        lines.append("|-----------|--------|--------|-----------------|-------------|--------|")
        for name, data in r.subsystems.items():
            loaded = "yes" if data.get("loaded") else "no"
            frames = data.get("frames_processed", data.get("frames_checked", data.get("frames_evaluated", "—")))
            dets = data.get("detections_total", data.get("masks_generated", data.get("total_faces_detected", data.get("total_events_generated", data.get("total_predictions", "—")))))
            lat = data.get("latency_ms_avg", "—")
            errs = len(data.get("errors", [])) + data.get("crashes", 0)
            lines.append(f"| {name} | {loaded} | {frames} | {dets} | {lat}ms | {errs} |")
        lines.append("")

    path = output_dir / "e2e_video_test_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=ROOT / "datasets" / "test_videos" / "manifest.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "storage" / "test_outputs")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--max-frames", type=int, default=300)
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading models on {args.device} ...")

    models: dict[str, Any] = {}
    load_errors: list[str] = []

    # Phone detector
    try:
        models["phone"] = _load_yolo_model("models/phone/current.pt", args.device)
        print(f"  phone detector: OK ({list(models['phone'].names.values())[:3]})")
    except Exception as exc:
        load_errors.append(f"phone: {exc}")
        print(f"  phone detector: FAILED — {exc}", file=sys.stderr)

    # Weapon detector
    try:
        models["weapon"] = _load_yolo_model("models/weapon/current.pt", args.device)
        print(f"  weapon detector: OK ({list(models['weapon'].names.values())[:5]})")
    except Exception as exc:
        load_errors.append(f"weapon: {exc}")
        print(f"  weapon detector: FAILED — {exc}", file=sys.stderr)

    # Violence detector
    try:
        models["violence"] = _load_yolo_model("models/anomaly/violence_yolo11.pt", args.device)
        print(f"  violence detector: OK")
    except Exception as exc:
        load_errors.append(f"violence: {exc}")
        print(f"  violence detector: FAILED — {exc}", file=sys.stderr)

    # Segmentation
    try:
        seg_svc, seg_err = _load_sam2(args.device)
        if seg_err:
            print(f"  segmentation: FAILED — {seg_err}", file=sys.stderr)
            load_errors.append(f"segmentation: {seg_err}")
        else:
            models["segmentation"] = seg_svc
            print(f"  segmentation (SAM2): OK (loaded={seg_svc.is_loaded()})")
    except Exception as exc:
        load_errors.append(f"segmentation: {exc}")
        print(f"  segmentation: FAILED — {exc}", file=sys.stderr)

    # Identity (face)
    try:
        models["identity"] = _load_insightface(args.device)
        print(f"  InsightFace buffalo_l: OK")
    except Exception as exc:
        load_errors.append(f"identity: {exc}")
        print(f"  InsightFace: FAILED — {exc}", file=sys.stderr)

    # Anomaly service
    try:
        models["anomaly"] = _load_anomaly_service()
        print(f"  anomaly service: OK")
    except Exception as exc:
        load_errors.append(f"anomaly: {exc}")
        print(f"  anomaly service: FAILED — {exc}", file=sys.stderr)

    # Rule engine (no preloading needed — instantiated per frame batch)
    models["rule_engine"] = True

    print(f"\nRunning E2E tests on {len(entries)} videos ...")
    all_results: list[VideoTestResult] = []

    for entry in entries:
        vid_id = entry["video_id"]
        print(f"\n  [{vid_id}] {entry.get('query', '')} ...")
        t0 = time.monotonic()
        result = _test_video(entry, models, args.max_frames, args.device)
        elapsed = time.monotonic() - t0
        status = "PASS" if result.passed else "FAIL"
        phone_dets = result.subsystems.get("phone_detector", {}).get("detections_total", 0)
        weapon_dets = result.subsystems.get("weapon_detector", {}).get("detections_total", 0)
        seg_masks = result.subsystems.get("segmentation", {}).get("masks_generated", 0)
        faces = result.subsystems.get("identity_face", {}).get("total_faces_detected", 0)
        print(f"    [{status}] {result.frames_sampled} frames | "
              f"phone={phone_dets} weapon={weapon_dets} seg_masks={seg_masks} faces={faces} | {elapsed:.1f}s")
        if result.failures:
            for f in result.failures:
                print(f"    FAIL: {f}")
        all_results.append(result)

    json_path = _write_json_report(all_results, args.output_dir)
    md_path = _write_markdown_report(all_results, args.output_dir)

    passed = sum(1 for r in all_results if r.passed)
    failed = len(all_results) - passed

    print(f"\n{'='*60}")
    print(f"E2E Test Results: {passed} passed / {failed} failed / {len(all_results)} total")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    if load_errors:
        print(f"\nModel load errors ({len(load_errors)}):")
        for e in load_errors:
            print(f"  - {e}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
