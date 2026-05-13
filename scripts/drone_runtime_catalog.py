from __future__ import annotations

import json
import os
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_ROOT = Path(
    os.environ.get(
        "AEGIS_DRONE_SIM_ENV_ROOT",
        r"C:\AegisExternalTools\drone_sim\runtime\environments",
    )
)
DEFAULT_INVENTORY_PATH = Path("storage/drone_sim/runtime_inventory.json")
DEFAULT_HOST = os.environ.get("AEGIS_AIRSIM_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AEGIS_AIRSIM_PORT", "41451"))


@dataclass(slots=True)
class RuntimeDefinition:
    name: str
    folder_hints: tuple[str, ...]
    executable_hints: tuple[str, ...]
    runtime_type: str


RUNTIME_DEFINITIONS: dict[str, RuntimeDefinition] = {
    "CityEnviron": RuntimeDefinition(
        name="CityEnviron",
        folder_hints=("CityEnviron", "CityEnvironment"),
        executable_hints=("CityEnviron.exe", "CityEnvironment.exe", "run.bat"),
        runtime_type="city",
    ),
    "AirSimNH": RuntimeDefinition(
        name="AirSimNH",
        folder_hints=("AirSimNH", "Neighborhood"),
        executable_hints=("AirSimNH.exe", "Neighborhood.exe", "run.bat"),
        runtime_type="neighborhood",
    ),
    "Blocks": RuntimeDefinition(
        name="Blocks",
        folder_hints=("Blocks",),
        executable_hints=("Blocks.exe", "run.bat"),
        runtime_type="fallback",
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_port_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def _iter_candidate_dirs(runtime_root: Path, hints: tuple[str, ...]) -> list[Path]:
    candidates: list[Path] = []
    if not runtime_root.exists():
        return candidates
    for entry in runtime_root.iterdir():
        if not entry.is_dir():
            continue
        name_lower = entry.name.lower()
        if any(hint.lower() in name_lower for hint in hints):
            candidates.append(entry)
    return sorted(candidates, key=lambda item: item.name.lower())


def _find_executable(runtime_dir: Path, hints: tuple[str, ...]) -> Path | None:
    for hint in hints:
        matches = list(runtime_dir.rglob(hint))
        if matches:
            return matches[0]
    for pattern in ("*.exe", "run.bat"):
        matches = list(runtime_dir.rglob(pattern))
        if matches:
            return matches[0]
    return None


def resolve_runtime_installation(
    runtime_name: str,
    *,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
) -> dict[str, Any]:
    definition = RUNTIME_DEFINITIONS.get(runtime_name)
    if definition is None:
        return {
            "name": runtime_name,
            "runtime_type": "unknown",
            "available": False,
            "reason": "unknown_runtime",
            "runtime_dir": None,
            "executable_path": None,
            "launcher_type": None,
        }

    import platform
    on_windows = platform.system() == "Windows"
    for candidate_dir in _iter_candidate_dirs(runtime_root, definition.folder_hints):
        executable = _find_executable(candidate_dir, definition.executable_hints)
        if executable is None:
            # Check if directory only contains a Linux build (.sh but no .exe)
            sh_files = list(candidate_dir.rglob("*.sh"))
            exe_files = list(candidate_dir.rglob("*.exe"))
            if sh_files and not exe_files and on_windows:
                return {
                    "name": definition.name,
                    "runtime_type": definition.runtime_type,
                    "available": False,
                    "reason": "linux_build_incompatible_on_windows",
                    "runtime_dir": str(candidate_dir.resolve()),
                    "executable_path": None,
                    "launcher_type": None,
                    "checked_at": now_iso(),
                }
            continue
        return {
            "name": definition.name,
            "runtime_type": definition.runtime_type,
            "available": True,
            "runtime_dir": str(candidate_dir.resolve()),
            "executable_path": str(executable.resolve()),
            "launcher_type": "bat" if executable.suffix.lower() == ".bat" else "exe",
            "checked_at": now_iso(),
        }

    return {
        "name": definition.name,
        "runtime_type": definition.runtime_type,
        "available": False,
        "reason": "missing_installation",
        "runtime_dir": None,
        "executable_path": None,
        "launcher_type": None,
        "checked_at": now_iso(),
    }


def discover_runtime_inventory(runtime_root: Path = DEFAULT_RUNTIME_ROOT) -> dict[str, Any]:
    runtimes = {
        name: resolve_runtime_installation(name, runtime_root=runtime_root)
        for name in ("CityEnviron", "AirSimNH", "Blocks")
    }
    available = [name for name, item in runtimes.items() if bool(item.get("available"))]
    return {
        "checked_at": now_iso(),
        "runtime_root": str(runtime_root.resolve()),
        "runtimes": runtimes,
        "available_runtimes": available,
    }


def persist_inventory(inventory: dict[str, Any], path: Path = DEFAULT_INVENTORY_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return path


def load_inventory(path: Path = DEFAULT_INVENTORY_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def select_runtime(
    *,
    prefer: str | None = None,
    fallback: str | None = None,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
) -> dict[str, Any]:
    inventory = discover_runtime_inventory(runtime_root)
    order: list[str] = []
    if prefer:
        order.append(prefer)
    if fallback:
        order.append(fallback)
    order.extend(["CityEnviron", "AirSimNH", "Blocks"])

    seen: set[str] = set()
    for candidate in order:
        if candidate in seen:
            continue
        seen.add(candidate)
        item = inventory["runtimes"].get(candidate)
        if item and item.get("available"):
            selected = dict(item)
            selected["fallback_used"] = selected.get("name") == "Blocks"
            selected["selection_order"] = order
            return selected

    return {
        "name": None,
        "runtime_type": "unknown",
        "available": False,
        "runtime_dir": None,
        "executable_path": None,
        "fallback_used": False,
        "selection_order": order,
    }


def latest_crash_summary(runtime_dir: Path) -> str | None:
    crashes_dir = runtime_dir / "Saved" / "Crashes"
    if not crashes_dir.exists():
        matches = list(runtime_dir.rglob("Saved/Crashes"))
        crashes_dir = matches[0] if matches else crashes_dir
    if not crashes_dir.exists():
        return None

    latest = max((p for p in crashes_dir.iterdir() if p.is_dir()), key=lambda item: item.stat().st_mtime, default=None)
    if latest is None:
        return None

    context_file = latest / "CrashContext.runtime-xml"
    if not context_file.exists():
        return f"Latest crash directory: {latest}"

    try:
        root = ET.fromstring(context_file.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError:
        return f"Latest crash directory: {latest}"

    def read_tag(tag: str) -> str:
        node = root.find(f".//{tag}")
        return node.text.strip() if node is not None and node.text else "unknown"

    return (
        f"Latest crash: {latest.name} | "
        f"type={read_tag('CrashType')} | "
        f"gpu={read_tag('Misc.PrimaryGPUBrand')} | "
        f"error={read_tag('ErrorMessage')}"
    )
