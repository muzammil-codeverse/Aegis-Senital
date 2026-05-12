#!/usr/bin/env python3
"""Full project validation: compileall, pytest collect, pytest, validate_runtime, npm build, optional CUDA smoke."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from shutil import which

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(cwd or ROOT))
    if rc != 0:
        raise SystemExit(rc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-smoke", action="store_true", help="Run optional CUDA smoke if torch is available")
    args = parser.parse_args()

    os.environ.setdefault("PYTHONFAULTHANDLER", "1")
    os.chdir(ROOT)

    run([sys.executable, "-m", "compileall", "backend", "inference", "ml", "scripts", "-q"])
    run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"])
    basetemp = ROOT / "storage" / "pytest_basetemp"
    basetemp.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-X",
            "faulthandler",
            "-m",
            "pytest",
            "tests/",
            "-q",
            f"--basetemp={basetemp}",
        ]
    )
    run([sys.executable, "scripts/validate_runtime.py", "--profile", "development"])
    npm = which("npm")
    if npm:
        run([npm, "run", "build"], cwd=ROOT / "frontend")
    else:
        print("[WARN] npm not found — skipping frontend build")

    if args.include_smoke:
        try:
            import torch

            if torch.cuda.is_available():
                print("[SMOKE] CUDA:", torch.cuda.get_device_name(0))
            else:
                print("[SMOKE] CUDA not available — skipped")
        except Exception as exc:
            print("[SMOKE] torch import failed:", exc)
    print("FULL VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
