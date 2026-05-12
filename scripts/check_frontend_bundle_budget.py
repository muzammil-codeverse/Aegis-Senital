#!/usr/bin/env python3
"""
Frontend bundle budget checker.
Inspects frontend/dist/assets after `npm run build` and warns/fails if chunk sizes exceed thresholds.

Thresholds:
  Warning:  single JS chunk > 750 KB (uncompressed)
  Failure:  single JS chunk > 1500 KB (uncompressed)
  Warning:  total JS size  > 3000 KB
  Failure:  total JS size  > 6000 KB

Run:
  python scripts/check_frontend_bundle_budget.py --warn-only
  python scripts/check_frontend_bundle_budget.py
"""
import argparse
import os
import sys

CHUNK_WARN_KB = 750
CHUNK_FAIL_KB = 1500
TOTAL_WARN_KB = 3000
TOTAL_FAIL_KB = 6000


def main():
    parser = argparse.ArgumentParser(description="Check frontend bundle budget")
    parser.add_argument("--warn-only", action="store_true", help="Only warn, never fail")
    parser.add_argument("--dist", default="frontend/dist/assets", help="Path to dist/assets")
    args = parser.parse_args()

    dist = args.dist
    if not os.path.isdir(dist):
        print(f"[bundle-budget] dist dir not found: {dist}")
        print("[bundle-budget] Run `npm run build` in frontend/ first.")
        sys.exit(0)

    js_files = [f for f in os.listdir(dist) if f.endswith(".js")]
    if not js_files:
        print("[bundle-budget] No JS files found in dist/assets — build may be empty.")
        sys.exit(0)

    warnings = []
    failures = []
    total_kb = 0

    for filename in sorted(js_files):
        path = os.path.join(dist, filename)
        size_bytes = os.path.getsize(path)
        size_kb = size_bytes / 1024
        total_kb += size_kb
        label = f"{filename} ({size_kb:.1f} KB)"
        if size_kb > CHUNK_FAIL_KB:
            failures.append(f"FAIL chunk too large: {label} > {CHUNK_FAIL_KB} KB limit")
        elif size_kb > CHUNK_WARN_KB:
            warnings.append(f"WARN chunk large:    {label} > {CHUNK_WARN_KB} KB warning")
        else:
            print(f"  ok  {label}")

    if total_kb > TOTAL_FAIL_KB:
        failures.append(f"FAIL total JS too large: {total_kb:.1f} KB > {TOTAL_FAIL_KB} KB limit")
    elif total_kb > TOTAL_WARN_KB:
        warnings.append(f"WARN total JS large: {total_kb:.1f} KB > {TOTAL_WARN_KB} KB warning")
    else:
        print(f"  ok  total JS: {total_kb:.1f} KB")

    for w in warnings:
        print(f"\n{w}")
    for f in failures:
        print(f"\n{f}")

    if failures and not args.warn_only:
        print("\n[bundle-budget] Budget exceeded — fix large chunks or raise thresholds.")
        sys.exit(1)
    elif warnings or failures:
        print("\n[bundle-budget] Warnings present — review chunk sizes.")
    else:
        print("\n[bundle-budget] All chunks within budget.")


if __name__ == "__main__":
    main()
