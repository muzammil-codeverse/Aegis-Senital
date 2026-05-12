#!/usr/bin/env python3
"""
Static accessibility smoke check for frontend JSX/HTML.
Checks for:
  - button elements with no text or aria-label
  - img elements with no alt or role="presentation"
  - input elements with no label or aria-label
  - icon-only buttons (detects lucide Icon components with no aria-label on parent button)

Run:
  python scripts/check_frontend_accessibility_static.py --warn-only
  python scripts/check_frontend_accessibility_static.py
"""
import argparse
import os
import re
import sys

SRC_DIR = "frontend/src"

PATTERNS = [
    (
        "button-no-label",
        re.compile(r'<button\b[^>]*>(\s*(?:<[A-Z][A-Za-z0-9]*[^/]*/?>)?\s*)</button>', re.DOTALL),
        "Button with likely no text label (icon-only button missing aria-label)",
    ),
    (
        "img-no-alt",
        re.compile(r'<img\b(?![^>]*\balt=)(?![^>]*role=["\']presentation["\'])[^>]*/?>'),
        "img element missing alt attribute",
    ),
    (
        "input-no-label",
        re.compile(r'<input\b(?![^>]*\baria-label=)(?![^>]*\bid=)[^>]*/?>'),
        "input element may be missing aria-label or id for label association",
    ),
]


def check_file(filepath, findings, warn_only):
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    for check_id, pattern, message in PATTERNS:
        for match in pattern.finditer(content):
            lineno = content[: match.start()].count("\n") + 1
            findings.append({
                "file": filepath,
                "line": lineno,
                "check": check_id,
                "message": message,
                "snippet": match.group(0)[:80].replace("\n", " "),
            })


def main():
    parser = argparse.ArgumentParser(description="Static frontend accessibility check")
    parser.add_argument("--warn-only", action="store_true", help="Only warn, never fail")
    parser.add_argument("--src", default=SRC_DIR)
    args = parser.parse_args()

    findings = []
    for root, _dirs, files in os.walk(args.src):
        for filename in files:
            if filename.endswith((".jsx", ".tsx", ".html")):
                check_file(os.path.join(root, filename), findings, args.warn_only)

    if not findings:
        print("[a11y-static] No accessibility issues found.")
        sys.exit(0)

    # Group by check type for summary
    from collections import Counter
    counts = Counter(f["check"] for f in findings)
    print(f"[a11y-static] {len(findings)} potential accessibility issue(s) found:\n")
    for f in findings[:40]:  # Cap output
        print(f"  {f['file']}:{f['line']} [{f['check']}] {f['message']}")
        print(f"    snippet: {f['snippet']}")
    if len(findings) > 40:
        print(f"  ... and {len(findings) - 40} more")
    print(f"\nSummary: {dict(counts)}")

    if not args.warn_only:
        sys.exit(1)
    print("\n[a11y-static] Running in warn-only mode — not failing.")


if __name__ == "__main__":
    main()
