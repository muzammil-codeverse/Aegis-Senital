"""Download exact Roboflow dataset versions used for local evaluation."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO_ROOT / "configs" / "evaluation" / "roboflow_sources.yaml"


def _load_sources() -> dict:
    with open(SOURCE_CONFIG, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or {}
    if not isinstance(sources, dict):
        raise RuntimeError(f"Invalid Roboflow source config: {SOURCE_CONFIG}")
    return sources


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _selected_sources(sources: dict, only: str | None, all_sources: bool) -> list[str]:
    if only and all_sources:
        raise RuntimeError("Use either --only or --all, not both")
    if only:
        if only not in sources:
            raise RuntimeError(f"Unknown source '{only}'. Available: {', '.join(sorted(sources))}")
        return [only]
    return list(sources.keys())


def _download_one(name: str, source: dict, api_key: str, force: bool) -> None:
    from roboflow import Roboflow

    workspace = source["workspace"]
    project_name = source["project"]
    version_number = int(source["version"])
    format_name = source.get("format", "yolov8")
    raw_dir = _resolve_repo_path(source["raw_dir"])

    if force and raw_dir.exists():
        shutil.rmtree(raw_dir)
    if raw_dir.exists() and not any(raw_dir.iterdir()):
        raw_dir.rmdir()
    raw_dir.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"Downloading {name}: workspace={workspace}, project={project_name}, "
        f"version={version_number}, format={format_name}"
    )
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(workspace).project(project_name)
    version = project.version(version_number)
    dataset = version.download(format_name, location=str(raw_dir), overwrite=force)
    print(f"Downloaded {name} dataset to {Path(dataset.location).resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("phone", "weapon"), help="Download only one dataset")
    parser.add_argument("--all", action="store_true", help="Download all configured datasets")
    parser.add_argument("--force", action="store_true", help="Delete existing raw_dir before downloading")
    args = parser.parse_args()

    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("ROBOFLOW_API_KEY is not set")

    sources = _load_sources()
    for name in _selected_sources(sources, args.only, args.all):
        _download_one(name, sources[name], api_key=api_key, force=args.force)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
