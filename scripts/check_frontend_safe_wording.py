from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
BANNED_PATTERNS = [
    "identity confirmed",
    "suspect confirmed",
    "target confirmed",
    "criminal confirmed",
    "guilty",
    "attacker confirmed",
    "real drone pursuit",
]


def should_scan(path: Path) -> bool:
    lowered = path.name.lower()
    if ".test." in lowered or ".spec." in lowered:
        return False
    return path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".css", ".md"}


def main() -> int:
    violations: list[str] = []

    for path in FRONTEND_SRC.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for phrase in BANNED_PATTERNS:
            for match in re.finditer(re.escape(phrase), lowered):
                line_number = lowered.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {phrase}")

    if violations:
        print("Frontend safe wording check failed:")
        for violation in violations:
            print(f" - {violation}")
        return 1

    print("Frontend safe wording check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
