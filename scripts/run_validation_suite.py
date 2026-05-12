#!/usr/bin/env python3
"""Standard validation entrypoint (Windows-friendly).

Sets PYTHONFAULTHANDLER=1 and runs pytest with a controlled basetemp under storage/pytest_basetemp.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.environ.setdefault("PYTHONFAULTHANDLER", "1")
    basetemp = ROOT / "storage" / "pytest_basetemp"
    basetemp.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-X",
        "faulthandler",
        "-m",
        "pytest",
        "tests/",
        "-q",
        f"--basetemp={basetemp}",
        *sys.argv[1:],
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
