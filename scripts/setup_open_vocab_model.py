#!/usr/bin/env python3
"""Download and configure the Open-Vocab (GroundingDINO) model for Aegis Sentinel.

Reads configs/runtime/open_vocab.yaml to detect the configured provider,
downloads the model from HuggingFace to a local path, updates the YAML
local_model_path, writes metadata.yaml, and prints AEGIS_OPEN_VOCAB_MODEL_PATH.

Usage:
  python scripts/setup_open_vocab_model.py
  python scripts/setup_open_vocab_model.py --provider grounding_dino --target models/open_vocab
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "configs" / "runtime" / "open_vocab.yaml"

PROVIDER_MODEL_IDS = {
    "grounding_dino": "IDEA-Research/grounding-dino-base",
    "grounding_dino_tiny": "IDEA-Research/grounding-dino-tiny",
}


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERROR: config not found: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _update_config(local_path: str) -> None:
    cfg = _load_config()
    cfg.setdefault("model", {})["local_model_path"] = local_path
    cfg.setdefault("model", {})["local_processor_path"] = local_path
    CONFIG_PATH.write_text(
        yaml.dump(cfg, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"  Updated {CONFIG_PATH} with local_model_path: {local_path}")


def _write_metadata(model_dir: Path, hf_repo_id: str, provider: str) -> None:
    import datetime
    meta = {
        "provider": provider,
        "hf_repo_id": hf_repo_id,
        "local_path": str(model_dir),
        "downloaded_at": datetime.datetime.utcnow().isoformat() + "Z",
        "aegis_env_var": "AEGIS_OPEN_VOCAB_MODEL_PATH",
        "aegis_env_value": str(model_dir),
    }
    meta_path = model_dir / "metadata.yaml"
    meta_path.write_text(
        yaml.dump(meta, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"  Metadata written: {meta_path}")


def _verify_load(model_path: str) -> bool:
    """Quick load-verify: check processor and model instantiate without error."""
    print(f"  Verifying model load from {model_path} ...")
    try:
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        import torch

        proc = AutoProcessor.from_pretrained(model_path, local_files_only=True)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(model_path, local_files_only=True)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
        model.eval()
        print(f"  Model loaded on {device} — OK")
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        return True
    except Exception as exc:
        print(f"  Load verify FAILED: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default=None, help="Override provider (default: from config)")
    parser.add_argument("--target", type=Path, default=ROOT / "models" / "open_vocab")
    parser.add_argument("--skip-download", action="store_true", help="Only update config, don't re-download")
    parser.add_argument("--no-verify", action="store_true", help="Skip load verification")
    args = parser.parse_args()

    cfg = _load_config()
    provider = args.provider or cfg.get("model", {}).get("provider", "grounding_dino")
    hf_repo_id = PROVIDER_MODEL_IDS.get(provider)
    if not hf_repo_id:
        print(f"ERROR: Unknown provider {provider!r}. Supported: {list(PROVIDER_MODEL_IDS)}", file=sys.stderr)
        sys.exit(1)

    model_dir = args.target / provider
    model_dir.mkdir(parents=True, exist_ok=True)

    print(f"Open-Vocab setup")
    print(f"  Provider: {provider}")
    print(f"  HuggingFace repo: {hf_repo_id}")
    print(f"  Local target: {model_dir}")

    # Check if already downloaded
    already_have = (model_dir / "config.json").exists() and (model_dir / "pytorch_model.bin").exists() or \
                   (model_dir / "config.json").exists() and any(model_dir.glob("*.safetensors"))

    if already_have and not args.skip_download:
        print(f"  Model files already present — skipping download")
    elif not args.skip_download:
        print(f"  Downloading {hf_repo_id} to {model_dir} ...")
        print(f"  (This may take several minutes — model is ~900MB)")
        try:
            from huggingface_hub import snapshot_download
            t0 = time.monotonic()
            snapshot_download(
                repo_id=hf_repo_id,
                local_dir=str(model_dir),
                local_dir_use_symlinks=False,
                ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
            )
            elapsed = time.monotonic() - t0
            print(f"  Download complete ({elapsed:.1f}s)")
        except Exception as exc:
            print(f"  Download failed: {exc}", file=sys.stderr)
            sys.exit(1)

    # Update config
    _update_config(str(model_dir))
    _write_metadata(model_dir, hf_repo_id, provider)

    # Verify load
    if not args.no_verify:
        ok = _verify_load(str(model_dir))
        if not ok:
            print(f"\nERROR: Model load verification failed.", file=sys.stderr)
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"AEGIS_OPEN_VOCAB_MODEL_PATH={model_dir}")
    print(f"\nSet in your shell:")
    print(f'  $env:AEGIS_OPEN_VOCAB_MODEL_PATH="{model_dir}"')
    print(f"\nOr add to .env:")
    print(f"  AEGIS_OPEN_VOCAB_MODEL_PATH={model_dir}")


if __name__ == "__main__":
    main()
