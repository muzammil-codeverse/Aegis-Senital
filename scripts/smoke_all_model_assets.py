#!/usr/bin/env python3
"""Phase 50 model-asset smoke validation.

Verifies that promoted model assets and their runtime adapters load under the
active Python environment without mutating registry pointers or hiding
degradations. Optional assets are reported honestly as degraded/skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


@dataclass
class CheckResult:
    name: str
    status: str
    required: bool
    detail: str = ""
    duration_seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def _emit(results: list[CheckResult], name: str, status: str, required: bool, detail: str = "", **extra: Any) -> None:
    icon = {
        "passed": "PASS",
        "failed": "FAIL",
        "degraded": "WARN",
        "skipped": "SKIP",
    }.get(status, status.upper())
    print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))
    results.append(CheckResult(name=name, status=status, required=required, detail=detail, extra=extra))


def _run_check(
    results: list[CheckResult],
    name: str,
    *,
    required: bool,
    fn,
) -> None:
    started = time.monotonic()
    try:
        detail, extra = fn()
    except SkipCheck as exc:
        _emit(results, name, "skipped", required, str(exc), duration_seconds=round(time.monotonic() - started, 3))
        return
    except OptionalDegradation as exc:
        _emit(results, name, "degraded", required, str(exc), duration_seconds=round(time.monotonic() - started, 3))
        return
    except Exception as exc:  # pragma: no cover - smoke scripts must stay broad
        _emit(results, name, "failed", required, str(exc), duration_seconds=round(time.monotonic() - started, 3))
        return
    extra = dict(extra or {})
    for key in ("name", "status", "required", "detail", "duration_seconds"):
        if key in extra:
            extra[f"meta_{key}"] = extra.pop(key)
    extra["duration_seconds"] = round(time.monotonic() - started, 3)
    _emit(results, name, "passed", required, detail, **extra)


class OptionalDegradation(RuntimeError):
    """Used when an optional asset is intentionally unavailable."""


class SkipCheck(RuntimeError):
    """Used when a check is intentionally skipped."""


def _resolve_device(requested: str) -> str:
    requested = (requested or "cpu").strip().lower()
    if requested != "cuda":
        return "cpu"
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _registry_active_entry(snapshot: dict[str, Any], model_key: str) -> tuple[str, dict[str, Any]]:
    block = snapshot.get(model_key)
    if not isinstance(block, dict):
        raise RuntimeError(f"registry entry missing for {model_key}")
    if "path" in block:
        return str(block.get("version") or "current"), block
    active_version = str(block.get("active_version") or "").strip()
    versions = {
        key: value
        for key, value in block.items()
        if key not in {"active_version", "active_rollout"} and isinstance(value, dict) and "path" in value
    }
    if active_version and active_version in versions:
        return active_version, versions[active_version]
    if not versions:
        raise RuntimeError(f"registry versions missing for {model_key}")
    version = sorted(versions)[-1]
    return version, versions[version]


def _make_clip(num_frames: int = 16, width: int = 224, height: int = 224) -> list[Any]:
    import numpy as np

    rng = np.random.default_rng(50)
    return [rng.integers(0, 255, size=(height, width, 3), dtype=np.uint8) for _ in range(num_frames)]


def _make_test_image() -> Any:
    import numpy as np

    image = np.full((512, 512, 3), 110, dtype=np.uint8)
    image[120:360, 170:330] = (40, 120, 180)
    image[350:430, 210:310] = (95, 70, 45)
    return image


def _load_open_vocab_config() -> dict[str, Any]:
    path = ROOT / "configs" / "runtime" / "open_vocab.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_open_vocab_path(cfg: dict[str, Any]) -> tuple[Path | None, bool]:
    env_path = str(os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH") or "").strip()
    if env_path:
        candidate = Path(env_path)
        return candidate, True
    rel_path = str((cfg.get("model") or {}).get("local_model_path") or "").strip()
    if not rel_path:
        return None, False
    candidate = Path(rel_path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate, True


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test all promoted model assets.")
    parser.add_argument("--device", default="cuda", help="Preferred device hint (cuda/cpu)")
    parser.add_argument("--json-out", default=None, help="Optional JSON summary output path")
    args = parser.parse_args()

    device = _resolve_device(args.device)
    print("=== Model Asset Smoke ===")
    print(f"  requested_device={args.device} resolved_device={device}")

    results: list[CheckResult] = []

    def registry_check() -> tuple[str, dict[str, Any]]:
        from app.repositories.model_registry_repository import get_model_registry_repository
        from ml.runtime.model_router import ModelRouter

        repository = get_model_registry_repository()
        snapshot = repository.read_snapshot()
        checks: list[str] = []
        for model_key in (
            "weapon_detector",
            "phone_detector",
            "face_recognition",
            "anomaly_pipeline",
            "segmentation_sam2",
            "reid_osnet",
            "open_vocab",
        ):
            version, entry = _registry_active_entry(snapshot, model_key)
            path_value = str(entry.get("path") or "").strip()
            logical_only = bool(entry.get("logical_only", False))
            optional_path = bool(entry.get("optional_path", False))
            if logical_only:
                checks.append(f"{model_key}:{version}=logical_only")
                continue
            resolved = Path(path_value)
            if not resolved.is_absolute():
                resolved = ROOT / resolved
            if resolved.exists():
                checks.append(f"{model_key}:{version}=present")
                continue
            if optional_path:
                checks.append(f"{model_key}:{version}=optional_missing")
                continue
            raise RuntimeError(f"{model_key}:{version} missing at {resolved}")
        resolved_models = ModelRouter().validate_required_models()
        return (
            f"registry active pointers resolved ({len(checks)} entries)",
            {
                "checks": checks,
                "router_weapon": resolved_models["weapon"]["resolved_path"],
                "router_phone": resolved_models["phone"]["resolved_path"],
            },
        )

    def yolo_phone_check() -> tuple[str, dict[str, Any]]:
        from ultralytics import YOLO

        path = ROOT / "models" / "phone" / "current.pt"
        model = YOLO(str(path))
        return (
            f"loaded {path}",
            {"task": getattr(model, "task", None), "names": getattr(model.model, "names", None)},
        )

    def yolo_weapon_check() -> tuple[str, dict[str, Any]]:
        from ultralytics import YOLO

        path = ROOT / "models" / "weapon" / "current.pt"
        model = YOLO(str(path))
        return (
            f"loaded {path}",
            {"task": getattr(model, "task", None), "names": getattr(model.model, "names", None)},
        )

    def yolo_violence_check() -> tuple[str, dict[str, Any]]:
        from ultralytics import YOLO

        path = ROOT / "models" / "anomaly" / "violence_yolo11.pt"
        model = YOLO(str(path))
        return (
            f"loaded {path}",
            {"task": getattr(model, "task", None), "names": getattr(model.model, "names", None)},
        )

    def videomae_check() -> tuple[str, dict[str, Any]]:
        from inference.anomaly.pretrained_adapter import PretrainedVideoAdapter

        model_path = ROOT / "models" / "anomaly" / "current"
        adapter = PretrainedVideoAdapter(model_path=str(model_path), device=device)
        adapter.load()
        if not adapter.is_loaded():
            raise RuntimeError(f"adapter failed to load: {adapter.health()}")
        prediction = adapter.predict_clip(_make_clip(), metadata={"camera_id": "smoke_cam_01", "window_seconds": 5.0})
        if prediction is None:
            raise RuntimeError("adapter loaded but predict_clip returned None")
        return (
            f"loaded {model_path} and produced score={prediction.score:.4f}",
            {
                "health_status": adapter.health().get("status"),
                "score": round(float(prediction.score), 4),
                "severity": prediction.severity,
            },
        )

    def insightface_check() -> tuple[str, dict[str, Any]]:
        from insightface.app import FaceAnalysis
        from ml.runtime.model_router import ModelRouter

        model_meta = ModelRouter().get_model("face")
        model_path = Path(model_meta["resolved_path"])
        providers = ["CPUExecutionProvider"]
        if device == "cuda":
            try:
                import onnxruntime as ort

                if "CUDAExecutionProvider" in ort.get_available_providers():
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            except Exception:
                providers = ["CPUExecutionProvider"]
        ctx_id = 0 if providers[0] == "CUDAExecutionProvider" else -1
        app = FaceAnalysis(name=model_path.name, root=str(model_path.parent.parent), providers=providers)
        app.prepare(ctx_id=ctx_id, det_size=(640, 640))
        return (
            f"loaded {model_path}",
            {"providers": providers, "ctx_id": ctx_id},
        )

    def reid_check() -> tuple[str, dict[str, Any]]:
        import numpy as np
        from torchreid.reid.utils import FeatureExtractor

        extractor = FeatureExtractor(model_name="osnet_x1_0", device=device)
        sample = np.zeros((256, 128, 3), dtype=np.uint8)
        embedding = extractor([sample]).cpu().numpy().reshape(-1)
        if embedding.size == 0:
            raise RuntimeError("OSNet returned an empty embedding")
        return (
            f"OSNet extractor returned embedding_dim={embedding.size}",
            {"embedding_dim": int(embedding.size), "device": device},
        )

    def sam2_check() -> tuple[str, dict[str, Any]]:
        from inference.segmentation.config import load_segmentation_config
        from inference.segmentation.sam2_adapter import Sam2SegmentationAdapter

        cfg = load_segmentation_config()
        cfg.device = device
        adapter = Sam2SegmentationAdapter(cfg)
        adapter.load()
        health = adapter.health()
        if not adapter.is_loaded():
            raise RuntimeError(f"SAM2 adapter not loaded: {health}")
        return (
            f"loaded {health['checkpoint_path']}",
            {"provider": health["provider"], "device": health["device"]},
        )

    def open_vocab_check() -> tuple[str, dict[str, Any]]:
        from inference.open_vocab.grounding_dino_adapter import GroundingDINOAdapter

        cfg = _load_open_vocab_config()
        resolved_path, configured = _resolve_open_vocab_path(cfg)
        required = bool((cfg.get("model") or {}).get("required", False))
        if not configured:
            raise OptionalDegradation("open-vocab model path is not configured")
        if resolved_path is None or not resolved_path.exists():
            if required:
                raise RuntimeError(f"configured open-vocab path missing: {resolved_path}")
            raise OptionalDegradation(f"configured open-vocab path missing: {resolved_path}")
        adapter_cfg = dict(cfg)
        model_cfg = dict(adapter_cfg.get("model") or {})
        model_cfg["local_model_path"] = str(resolved_path)
        model_cfg["local_processor_path"] = str(resolved_path)
        model_cfg["device_preference"] = device
        adapter_cfg["model"] = model_cfg
        adapter = GroundingDINOAdapter(config=adapter_cfg)
        adapter.load()
        status = adapter.get_status()
        if not adapter.is_available():
            if required:
                raise RuntimeError(f"adapter unavailable: {status.get('reason')}")
            raise OptionalDegradation(f"adapter unavailable: {status.get('reason')}")
        detections = adapter.detect(_make_test_image(), ["weapon", "phone"], thresholds={"box_threshold": 0.25, "text_threshold": 0.2})
        return (
            f"loaded {resolved_path}",
            {"device": status.get("device"), "detections": len(detections)},
        )

    _run_check(results, "model registry current pointers", required=True, fn=registry_check)
    _run_check(results, "phone YOLO", required=True, fn=yolo_phone_check)
    _run_check(results, "weapon YOLO", required=True, fn=yolo_weapon_check)
    _run_check(results, "violence YOLO", required=True, fn=yolo_violence_check)
    _run_check(results, "anomaly VideoMAE", required=True, fn=videomae_check)
    _run_check(results, "InsightFace buffalo_l", required=True, fn=insightface_check)
    _run_check(results, "ReID OSNet", required=True, fn=reid_check)
    _run_check(results, "SAM2", required=True, fn=sam2_check)
    _run_check(results, "Open-Vocab GroundingDINO", required=False, fn=open_vocab_check)

    failed_required = any(item.required and item.status == "failed" for item in results)
    degraded_optional = any((not item.required) and item.status in {"degraded", "skipped"} for item in results)
    overall = "failed" if failed_required else ("passed_with_degraded_optional" if degraded_optional else "passed")

    summary = {
        "script": "scripts/smoke_all_model_assets.py",
        "generated_at": time.time(),
        "requested_device": args.device,
        "resolved_device": device,
        "overall": overall,
        "results": [asdict(item) for item in results],
    }

    print()
    print(f"Overall: {overall}")
    if args.json_out:
        _save_json(Path(args.json_out), summary)
        print(f"Summary JSON: {args.json_out}")

    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
