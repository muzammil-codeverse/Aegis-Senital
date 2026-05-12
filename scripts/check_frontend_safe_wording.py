from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"
FRONTEND_PUBLIC = ROOT / "frontend" / "public"

# Phrases that must never appear in production frontend source or public assets.
# All comparisons are case-insensitive.
BANNED_PATTERNS = [
    "identity confirmed",
    "suspect confirmed",
    "target confirmed",
    "criminal confirmed",
    "attacker confirmed",
    "guilty",
    "real drone pursuit",
    "confirmed threat",
    "confirmed terrorist",
]

# Tokens that, when present on a line, indicate the line is a test assertion
# verifying that banned wording is blocked — not actual usage.
_ASSERTION_TOKENS = ("assert", "expect", "forbidden", "FORBIDDEN")


def should_scan(path: Path) -> bool:
    """Return True if this file should be checked for banned phrases.

    Exclusions:
    - Test files (.test.js, .test.jsx, .test.ts, .test.tsx, .spec.*) — these
      may contain banned phrases inside assertions that verify the phrases are
      blocked.
    - Documentation files under docs/ — policy explanations may quote banned
      phrases for illustration.
    - Markdown files anywhere — same documentation rationale.
    """
    lowered = path.name.lower()

    # Skip test/spec files entirely — they assert bans are enforced.
    if ".test." in lowered or ".spec." in lowered:
        return False

    # Skip markdown files — documentation that describes the policy may quote
    # forbidden phrases.
    if path.suffix.lower() == ".md":
        return False

    # Skip anything inside a docs/ directory.
    try:
        path.relative_to(ROOT / "docs")
        return False
    except ValueError:
        pass

    return path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".css", ".html"}


def _is_assertion_line(line: str) -> bool:
    """Return True if the line is a test assertion referencing the banned phrase
    as the thing being checked, not as live UI content."""
    return any(token in line for token in _ASSERTION_TOKENS)


def scan_tree(root: Path, violations: list[str]) -> None:
    """Recursively scan all files under *root* and append violations."""
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        lowered_lines = [line.lower() for line in lines]
        for phrase in BANNED_PATTERNS:
            for line_idx, lowered_line in enumerate(lowered_lines):
                if phrase in lowered_line:
                    # Skip lines that are assertion/test helpers verifying bans.
                    if _is_assertion_line(lines[line_idx]):
                        continue
                    line_number = line_idx + 1
                    violations.append(
                        f"{path.relative_to(ROOT)}:{line_number}: '{phrase}'"
                    )


def main() -> int:
    violations: list[str] = []

    scan_tree(FRONTEND_SRC, violations)
    scan_tree(FRONTEND_PUBLIC, violations)

    if violations:
        print("Frontend safe wording check FAILED — forbidden phrases found:")
        for violation in violations:
            print(f"  {violation}")
        return 1

    print("Frontend safe wording check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
