#!/usr/bin/env python3
"""
Static accessibility smoke check for frontend JSX/HTML.
Checks for:
  - button elements with no text or aria-label
  - img elements with no alt or role="presentation"
  - input elements with no label or aria-label

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
        # Matches <input ...> or <input .../> tags that stop at the first > (may be inside JSX handler)
        re.compile(r'<input\b[^>]*/?>'),
        "input element may be missing aria-label or id for label association",
    ),
]

_LABEL_OPEN = re.compile(r'<label\b')
_LABEL_CLOSE = re.compile(r'</label\s*>')

# Scan ahead up to this many characters to find the real end of an input tag
# when the tag spans multiple lines or contains JSX arrow functions.
_TAG_SCAN_LIMIT = 800


def _get_full_tag(content, match_start):
    """Return the full input tag text, handling multi-line and JSX arrow functions."""
    # Start from match_start and scan for the closing />
    scan = content[match_start: match_start + _TAG_SCAN_LIMIT]
    # Find /> that closes the self-closing input tag
    end = re.search(r'/>', scan)
    if end:
        return scan[: end.end()]
    # Fallback: single > close
    end = re.search(r'(?<!=)>(?!\s*<)', scan)
    if end:
        return scan[: end.end()]
    return scan[:200]


def _tag_has_label(tag_text):
    """Return True if the tag text contains aria-label= or id=."""
    return bool(re.search(r'\baria-label=', tag_text) or re.search(r'\bid=', tag_text))


def _is_inside_label(content, match_start):
    """Return True if the match position appears to be inside a <label> element.

    Find the last <label> open position and last </label> close position that
    both appear before the match.  If the last open is closer to the match
    than the last close, the input is inside an open label.
    """
    preceding = content[:match_start]
    opens = [m.start() for m in _LABEL_OPEN.finditer(preceding)]
    closes = [m.start() for m in _LABEL_CLOSE.finditer(preceding)]
    if not opens:
        return False
    last_open = opens[-1]
    if not closes:
        return True
    return last_open > closes[-1]


def check_file(filepath, findings, warn_only):
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    for check_id, pattern, message in PATTERNS:
        for match in pattern.finditer(content):
            if check_id == "input-no-label":
                # Get the full tag (across arrow functions / multi-line)
                full_tag = _get_full_tag(content, match.start())
                # Skip if the full tag already has aria-label= or id=
                if _tag_has_label(full_tag):
                    continue
                # Skip if inside a <label> element
                if _is_inside_label(content, match.start()):
                    continue
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

    from collections import Counter
    counts = Counter(f["check"] for f in findings)
    print(f"[a11y-static] {len(findings)} potential accessibility issue(s) found:\n")
    for f in findings[:40]:
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
