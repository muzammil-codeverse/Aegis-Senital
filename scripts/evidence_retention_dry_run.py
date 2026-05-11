#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.evidence_retention_service import get_evidence_retention_service


def main() -> int:
    parser = argparse.ArgumentParser(description="List evidence retention candidates without deleting files.")
    parser.add_argument("--case-id", default=None)
    args = parser.parse_args()

    candidates = get_evidence_retention_service().dry_run(case_id=args.case_id)
    payload = {
        "case_id": args.case_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "deleted": False,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
