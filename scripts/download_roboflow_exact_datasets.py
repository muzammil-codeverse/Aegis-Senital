"""Download Roboflow datasets for Aegis Sentinel evaluation and training.

Usage examples:
  python scripts/download_roboflow_exact_datasets.py --task phone
  python scripts/download_roboflow_exact_datasets.py --task weapon
  python scripts/download_roboflow_exact_datasets.py --task weapon --source primary_indonesian
  python scripts/download_roboflow_exact_datasets.py --all
  python scripts/download_roboflow_exact_datasets.py --list-sources
  python scripts/download_roboflow_exact_datasets.py --task weapon --continue-on-error

Requires ROBOFLOW_API_KEY environment variable.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

# Ensure UTF-8 output on Windows consoles with legacy code pages.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO_ROOT / "configs" / "evaluation" / "roboflow_sources.yaml"
MANIFEST_PATH = REPO_ROOT / "datasets" / "raw" / "download_manifest.json"

# Top-level task keys whose value is a single source dict (not a group).
_SINGLE_SOURCE_TASKS = ("phone", "weapon")


def _load_config() -> dict:
    with open(SOURCE_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise RuntimeError(f"Invalid source config: {SOURCE_CONFIG}")
    return cfg


def _resolve_path(value: str) -> Path:
    p = Path(value)
    return (REPO_ROOT / p).resolve() if not p.is_absolute() else p.resolve()


def _all_sources(cfg: dict) -> dict[str, dict]:
    """Return flat name→source_dict for every downloadable entry."""
    result: dict[str, dict] = {}
    for key, value in cfg.items():
        if not isinstance(value, dict):
            continue
        # top-level single source (phone, weapon)
        if "workspace" in value:
            result[key] = value
        else:
            # group of sources (weapon_sources)
            for src_name, src_cfg in value.items():
                if isinstance(src_cfg, dict) and "workspace" in src_cfg:
                    result[src_name] = src_cfg
    return result


def _sources_for_task(cfg: dict, task: str) -> dict[str, dict]:
    """Return sources that belong to a task.

    Priority: group key ({task}_sources) wins over single top-level key ({task}).
    phone ->cfg['phone']  (no group exists)
    weapon ->cfg['weapon_sources']  (group takes priority over cfg['weapon'])
    """
    # Check for a multi-source group first
    group_key = f"{task}_sources"
    group = cfg.get(group_key)
    if group and isinstance(group, dict):
        return {
            name: src
            for name, src in group.items()
            if isinstance(src, dict) and "workspace" in src
        }
    # Fall back to a single top-level entry
    entry = cfg.get(task)
    if entry and isinstance(entry, dict) and "workspace" in entry:
        return {task: entry}
    return {}


def _list_sources(cfg: dict) -> None:
    print(f"{'NAME':<35} {'WORKSPACE':<30} {'PROJECT':<40} {'VER':<6} ROLE")
    print("-" * 120)
    for name, src in _all_sources(cfg).items():
        ver = str(src.get("version") or "latest")
        role = src.get("role", "")
        print(
            f"{name:<35} {src['workspace']:<30} {src['project']:<40} {ver:<6} {role}"
        )


def _get_latest_version(project_obj: Any) -> int:
    """Return the highest published version number for a Roboflow project."""
    try:
        versions = project_obj.versions()
        if not versions:
            raise RuntimeError("No versions found for project")
        return max(v.version for v in versions)
    except Exception as exc:
        raise RuntimeError(f"Could not retrieve versions: {exc}") from exc


def _download_one(name: str, source: dict, api_key: str, force: bool) -> dict:
    """Download a single dataset. Returns a manifest entry dict."""
    from roboflow import Roboflow  # import late so --list-sources works without roboflow

    workspace = source["workspace"]
    project_name = source["project"]
    version_number = source.get("version")
    format_name = source.get("format", "yolov8")
    raw_dir = _resolve_path(source["raw_dir"])

    if force and raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n[{name}] workspace={workspace}  project={project_name}  format={format_name}")

    rf = Roboflow(api_key=api_key)
    project = rf.workspace(workspace).project(project_name)

    if version_number is None:
        print(f"[{name}] version=null - resolving latest ...")
        version_number = _get_latest_version(project)
        print(f"[{name}] latest version resolved to v{version_number}")
    else:
        version_number = int(version_number)
        print(f"[{name}] version={version_number}")

    version = project.version(version_number)
    dataset = version.download(format_name, location=str(raw_dir), overwrite=force)
    actual_dir = Path(dataset.location).resolve()
    print(f"[{name}] downloaded ->{actual_dir}")

    return {
        "name": name,
        "workspace": workspace,
        "project": project_name,
        "version": version_number,
        "format": format_name,
        "status": "downloaded",
        "raw_dir": str(raw_dir.relative_to(REPO_ROOT)),
        "actual_dir": str(actual_dir),
        "error": None,
    }


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"downloaded_at": None, "sources": []}


def _save_manifest(entries: list[dict]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_manifest()
    existing_by_name = {e["name"]: e for e in existing.get("sources", [])}
    for entry in entries:
        existing_by_name[entry["name"]] = entry
    manifest = {
        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sources": list(existing_by_name.values()),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest written ->{MANIFEST_PATH.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    task_group = parser.add_mutually_exclusive_group()
    task_group.add_argument(
        "--task",
        choices=("phone", "weapon"),
        help="Download datasets for a specific task",
    )
    task_group.add_argument("--all", action="store_true", help="Download all configured datasets")
    parser.add_argument(
        "--source",
        metavar="SOURCE_NAME",
        help="Download a specific named source within --task weapon (e.g. primary_indonesian)",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="List all configured sources and exit (no download)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue downloading remaining sources if one fails",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing raw_dir before downloading",
    )
    args = parser.parse_args()

    cfg = _load_config()

    if args.list_sources:
        _list_sources(cfg)
        return 0

    if not args.task and not args.all:
        parser.error("Specify --task <phone|weapon>, --all, or --list-sources")

    if args.source and args.task != "weapon":
        parser.error("--source can only be used with --task weapon")

    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("ERROR: ROBOFLOW_API_KEY environment variable is not set.", file=sys.stderr)
        return 1

    # Build the set of sources to download
    if args.all:
        selected = _all_sources(cfg)
    else:
        selected = _sources_for_task(cfg, args.task)
        if not selected:
            print(f"ERROR: No sources found for task '{args.task}'.", file=sys.stderr)
            return 1

    if args.source:
        if args.source not in selected:
            available = ", ".join(sorted(selected))
            print(
                f"ERROR: Source '{args.source}' not found for task '{args.task}'. "
                f"Available: {available}",
                file=sys.stderr,
            )
            return 1
        selected = {args.source: selected[args.source]}

    print(f"Downloading {len(selected)} source(s): {', '.join(selected)}")

    results: list[dict] = []
    errors: list[str] = []

    for name, source in selected.items():
        try:
            entry = _download_one(name, source, api_key=api_key, force=args.force)
            results.append(entry)
        except Exception as exc:
            msg = f"[{name}] FAILED: {exc}"
            print(f"ERROR: {msg}", file=sys.stderr)
            results.append(
                {
                    "name": name,
                    "workspace": source.get("workspace", ""),
                    "project": source.get("project", ""),
                    "version": source.get("version"),
                    "format": source.get("format", "yolov8"),
                    "status": "failed",
                    "raw_dir": source.get("raw_dir", ""),
                    "actual_dir": None,
                    "error": str(exc),
                }
            )
            errors.append(msg)
            if not args.continue_on_error:
                _save_manifest(results)
                return 1

    _save_manifest(results)

    if errors:
        print(f"\n{len(errors)} source(s) failed:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"\nAll {len(results)} source(s) downloaded successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
