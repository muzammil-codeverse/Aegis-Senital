from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_RUNTIME_DIR = Path(
    os.environ.get(
        "AEGIS_DRONE_SIM_RUNTIME_DIR",
        r"C:\AegisExternalTools\drone_sim\runtime",
    )
)
DEFAULT_BLOCKS_RELATIVE = Path(
    r"environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks.exe"
)
DEFAULT_HOST = os.environ.get("AEGIS_AIRSIM_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AEGIS_AIRSIM_PORT", "41451"))
DEFAULT_ARGS = ["-windowed", "-ResX=640", "-ResY=480"]


def resolve_blocks_executable(runtime_dir: Path) -> Path:
    explicit = runtime_dir / DEFAULT_BLOCKS_RELATIVE
    if explicit.exists():
        return explicit

    matches = sorted(runtime_dir.rglob("Blocks.exe"))
    if matches:
        return matches[0]

    raise FileNotFoundError(
        f"Could not locate Blocks.exe under {runtime_dir}. "
        "Download or extract the Cosys-AirSim Blocks runtime first."
    )


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def read_latest_crash_summary(runtime_dir: Path) -> str | None:
    crashes_dir = runtime_dir / "environments" / "Blocks"
    crash_root = crashes_dir / "Blocks_packaged_Windows_55_33" / "Windows" / "Blocks" / "Saved" / "Crashes"
    if not crash_root.exists():
        return None

    latest = max((p for p in crash_root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, default=None)
    if latest is None:
        return None

    context_file = latest / "CrashContext.runtime-xml"
    if not context_file.exists():
        return f"Latest crash folder: {latest}"

    try:
        root = ET.fromstring(context_file.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError:
        return f"Latest crash folder: {latest}"

    def read_tag(tag: str) -> str:
        node = root.find(f".//{tag}")
        return node.text.strip() if node is not None and node.text else "unknown"

    crash_type = read_tag("CrashType")
    error_message = read_tag("ErrorMessage")
    command_line = read_tag("CommandLine")
    gpu = read_tag("Misc.PrimaryGPUBrand")
    return (
        f"Latest crash: {latest.name} | type={crash_type} | gpu={gpu} | "
        f"error={error_message} | command={command_line}"
    )


def launch_blocks(executable: Path, extra_args: list[str]) -> subprocess.Popen[bytes]:
    args = [str(executable), *DEFAULT_ARGS, *extra_args]
    return subprocess.Popen(
        args,
        cwd=str(executable.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the Cosys-AirSim Blocks runtime with stable defaults.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR), help="Base runtime directory")
    parser.add_argument("--host", default=DEFAULT_HOST, help="AirSim RPC host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="AirSim RPC port")
    parser.add_argument("--timeout", type=int, default=45, help="Seconds to wait for the RPC port")
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Additional argument to pass to Blocks.exe; can be provided multiple times.",
    )
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    try:
        executable = resolve_blocks_executable(runtime_dir)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    if is_port_open(args.host, args.port):
        print(f"Blocks runtime already reachable at {args.host}:{args.port}")
        print(f"Executable: {executable}")
        return 0

    print(f"Launching: {executable} {' '.join(DEFAULT_ARGS + args.extra_arg)}")
    launch_blocks(executable, args.extra_arg)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if is_port_open(args.host, args.port):
            print(f"Blocks runtime reachable at {args.host}:{args.port}")
            return 0
        time.sleep(1)

    print(f"Blocks runtime did not open {args.host}:{args.port} within {args.timeout}s.")
    summary = read_latest_crash_summary(runtime_dir)
    if summary:
        print(summary)
    print(
        "Manual resolution if the Unreal fatal error persists: "
        "launch Blocks in windowed low-resolution mode, then force "
        "Windows Graphics Settings or the NVIDIA Control Panel to use the "
        "high-performance GPU for Blocks.exe."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
