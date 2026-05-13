from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

try:
    from scripts.drone_runtime_catalog import (
        DEFAULT_INVENTORY_PATH,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        now_iso,
        persist_inventory,
        resolve_runtime_installation,
        select_runtime,
    )
except ModuleNotFoundError:
    from drone_runtime_catalog import (  # type: ignore[no-redef]
        DEFAULT_INVENTORY_PATH,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        now_iso,
        persist_inventory,
        resolve_runtime_installation,
        select_runtime,
    )

GITHUB_RELEASES_API = "https://api.github.com/repos/microsoft/AirSim/releases"


def _fetch_release_assets(timeout: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "aegis-sentinel-phase55",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assets: list[dict[str, Any]] = []
    for release in payload:
        for asset in release.get("assets") or []:
            assets.append(
                {
                    "release_tag": release.get("tag_name"),
                    "release_name": release.get("name"),
                    "asset_name": asset.get("name"),
                    "download_url": asset.get("browser_download_url"),
                    "size": asset.get("size"),
                    "updated_at": asset.get("updated_at"),
                }
            )
    return assets


def _runtime_asset_candidates(runtime_name: str, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runtime_key = runtime_name.lower()
    candidates: list[dict[str, Any]] = []
    for asset in assets:
        filename = str(asset.get("asset_name") or "").lower()
        if runtime_key not in filename:
            continue
        if ".zip" not in filename:
            continue
        candidates.append(asset)
    candidates.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return candidates


def _download_with_resume(url: str, destination: Path, timeout: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    offset = destination.stat().st_size if destination.exists() else 0
    headers = {"User-Agent": "aegis-sentinel-phase55"}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            mode = "ab" if offset > 0 and status == 206 else "wb"
            with destination.open(mode) as handle:
                shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        if exc.code == 416 and offset > 0:
            destination.unlink(missing_ok=True)
            fresh_request = urllib.request.Request(url, headers={"User-Agent": "aegis-sentinel-phase55"})
            with urllib.request.urlopen(fresh_request, timeout=timeout) as response:
                with destination.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            return
        raise


def _verify_zip(zip_path: Path) -> tuple[bool, str | None]:
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            broken = archive.testzip()
            if broken:
                return False, f"zip entry failed integrity check: {broken}"
        return True, None
    except Exception as exc:
        return False, str(exc)


def _extract_standard_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(target_dir)


def _extract_multipart_zip(first_part: Path, target_dir: Path) -> tuple[bool, str | None]:
    seven_zip = shutil.which("7z") or shutil.which("7zz")
    if not seven_zip:
        return False, "7z/7zz is not available for multipart archive extraction"
    target_dir.mkdir(parents=True, exist_ok=True)
    command = [seven_zip, "x", str(first_part), f"-o{target_dir}", "-y"]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if completed.returncode != 0:
        return False, "\n".join(completed.stdout.splitlines()[-10:])
    return True, None


def _find_multipart_group(runtime_name: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_parts = [item for item in candidates if str(item.get("asset_name") or "").lower().endswith(".zip.001")]
    if not first_parts:
        return []
    first = first_parts[0]
    base = str(first.get("asset_name") or "")[:-4]
    group = [item for item in candidates if str(item.get("asset_name") or "").startswith(base)]
    group.sort(key=lambda item: str(item.get("asset_name") or ""))
    return group


def _record_inventory(
    *,
    runtime_root: Path,
    prefer: str,
    fallback: str,
    selection_reason: str,
    download_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inventory = discover_runtime_inventory(runtime_root)
    selected = select_runtime(prefer=prefer, fallback=fallback, runtime_root=runtime_root)
    inventory["selected_runtime"] = selected.get("name")
    inventory["selected_runtime_details"] = selected
    inventory["selection_reason"] = selection_reason
    inventory["download_status"] = download_status or {}
    inventory["updated_at"] = now_iso()
    persist_inventory(inventory, DEFAULT_INVENTORY_PATH)
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a precompiled AirSim city/neighborhood runtime outside the repository.")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--fallback", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)

    already = resolve_runtime_installation(args.prefer, runtime_root=runtime_root)
    if already.get("available") and not args.force:
        inventory = _record_inventory(
            runtime_root=runtime_root,
            prefer=args.prefer,
            fallback=args.fallback,
            selection_reason="already_installed",
            download_status={"runtime": args.prefer, "status": "already_installed"},
        )
        print(json.dumps({"status": "ok", "inventory": inventory, "message": "Runtime already installed."}, indent=2))
        return 0

    try:
        assets = _fetch_release_assets(timeout=args.timeout)
    except Exception as exc:
        inventory = _record_inventory(
            runtime_root=runtime_root,
            prefer=args.prefer,
            fallback=args.fallback,
            selection_reason="asset_listing_failed",
            download_status={"runtime": args.prefer, "status": "failed", "reason": str(exc)},
        )
        print(json.dumps({"status": "failed", "reason": f"Asset listing failed: {exc}", "inventory": inventory}, indent=2))
        return 1

    runtime_to_download = args.prefer
    candidates = _runtime_asset_candidates(runtime_to_download, assets)
    if not candidates and args.fallback and args.fallback != args.prefer:
        runtime_to_download = args.fallback
        candidates = _runtime_asset_candidates(runtime_to_download, assets)

    if not candidates:
        inventory = _record_inventory(
            runtime_root=runtime_root,
            prefer=args.prefer,
            fallback=args.fallback,
            selection_reason="download_unavailable",
            download_status={
                "runtime": runtime_to_download,
                "status": "failed",
                "reason": "no_release_asset_found",
            },
        )
        print(json.dumps({"status": "failed", "reason": "No matching runtime asset found in AirSim releases.", "inventory": inventory}, indent=2))
        return 1

    multipart_group = _find_multipart_group(runtime_to_download, candidates)
    use_multipart = bool(multipart_group)
    download_plan = multipart_group if multipart_group else [candidates[0]]
    downloaded_files: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="aegis_airsim_dl_") as temp_dir:
        temp_root = Path(temp_dir)
        for asset in download_plan:
            asset_name = str(asset.get("asset_name") or "")
            url = str(asset.get("download_url") or "")
            if not asset_name or not url:
                inventory = _record_inventory(
                    runtime_root=runtime_root,
                    prefer=args.prefer,
                    fallback=args.fallback,
                    selection_reason="download_metadata_invalid",
                    download_status={"runtime": runtime_to_download, "status": "failed", "reason": "missing_asset_name_or_url"},
                )
                print(json.dumps({"status": "failed", "reason": "Asset metadata incomplete", "inventory": inventory}, indent=2))
                return 1
            destination = temp_root / asset_name
            try:
                _download_with_resume(url, destination, args.timeout)
            except Exception as exc:
                inventory = _record_inventory(
                    runtime_root=runtime_root,
                    prefer=args.prefer,
                    fallback=args.fallback,
                    selection_reason="download_failed",
                    download_status={"runtime": runtime_to_download, "status": "failed", "reason": str(exc), "asset": asset_name},
                )
                print(json.dumps({"status": "failed", "reason": f"Download failed for {asset_name}: {exc}", "inventory": inventory}, indent=2))
                return 1
            expected_size = int(asset.get("size") or 0)
            actual_size = destination.stat().st_size if destination.exists() else 0
            if expected_size and actual_size < expected_size:
                inventory = _record_inventory(
                    runtime_root=runtime_root,
                    prefer=args.prefer,
                    fallback=args.fallback,
                    selection_reason="download_incomplete",
                    download_status={
                        "runtime": runtime_to_download,
                        "status": "failed",
                        "reason": "download_incomplete",
                        "asset": asset_name,
                        "expected_size": expected_size,
                        "actual_size": actual_size,
                    },
                )
                print(json.dumps({"status": "failed", "reason": f"Incomplete download for {asset_name}", "inventory": inventory}, indent=2))
                return 1
            downloaded_files.append(destination)

        runtime_target_dir = runtime_root / runtime_to_download
        if runtime_target_dir.exists() and args.force:
            shutil.rmtree(runtime_target_dir, ignore_errors=True)

        if use_multipart:
            first_part = next((item for item in downloaded_files if item.name.lower().endswith(".zip.001")), downloaded_files[0])
            ok, reason = _extract_multipart_zip(first_part, runtime_target_dir)
            if not ok:
                inventory = _record_inventory(
                    runtime_root=runtime_root,
                    prefer=args.prefer,
                    fallback=args.fallback,
                    selection_reason="extract_failed",
                    download_status={"runtime": runtime_to_download, "status": "failed", "reason": reason, "multipart": True},
                )
                print(json.dumps({"status": "failed", "reason": reason, "inventory": inventory}, indent=2))
                return 1
        else:
            zip_file = downloaded_files[0]
            zip_ok, zip_reason = _verify_zip(zip_file)
            if not zip_ok:
                inventory = _record_inventory(
                    runtime_root=runtime_root,
                    prefer=args.prefer,
                    fallback=args.fallback,
                    selection_reason="integrity_failed",
                    download_status={"runtime": runtime_to_download, "status": "failed", "reason": zip_reason},
                )
                print(json.dumps({"status": "failed", "reason": f"ZIP integrity failed: {zip_reason}", "inventory": inventory}, indent=2))
                return 1
            try:
                _extract_standard_zip(zip_file, runtime_target_dir)
            except Exception as exc:
                inventory = _record_inventory(
                    runtime_root=runtime_root,
                    prefer=args.prefer,
                    fallback=args.fallback,
                    selection_reason="extract_failed",
                    download_status={"runtime": runtime_to_download, "status": "failed", "reason": str(exc)},
                )
                print(json.dumps({"status": "failed", "reason": f"Extraction failed: {exc}", "inventory": inventory}, indent=2))
                return 1

    verified = resolve_runtime_installation(runtime_to_download, runtime_root=runtime_root)
    if not verified.get("available"):
        inventory = _record_inventory(
            runtime_root=runtime_root,
            prefer=args.prefer,
            fallback=args.fallback,
            selection_reason="verify_failed",
            download_status={"runtime": runtime_to_download, "status": "failed", "reason": "runtime_not_detected_after_extract"},
        )
        print(json.dumps({"status": "failed", "reason": "Runtime extracted but executable was not detected.", "inventory": inventory}, indent=2))
        return 1

    inventory = _record_inventory(
        runtime_root=runtime_root,
        prefer=args.prefer,
        fallback=args.fallback,
        selection_reason="downloaded",
        download_status={
            "runtime": runtime_to_download,
            "status": "ok",
            "multipart": use_multipart,
            "downloaded_at": now_iso(),
        },
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "runtime": runtime_to_download,
                "verified": verified,
                "selected_runtime": inventory.get("selected_runtime"),
                "inventory_path": str(DEFAULT_INVENTORY_PATH.resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
