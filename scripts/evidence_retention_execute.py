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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute reviewed evidence retention actions.")
    parser.add_argument("--mode", choices=("quarantine", "delete"), required=True)
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--all", action="store_true", help="Apply the retention action to all eligible cases")
    parser.add_argument("--require-review", action="store_true", help="Confirm the action was explicitly reviewed")
    parser.add_argument("--reviewed-by", default="reviewed")
    parser.add_argument("--requested-by", default="system")
    parser.add_argument("--confirm-delete", default=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.case_id and args.all:
        parser.error("--case-id and --all are mutually exclusive")
    if not args.case_id and not args.all:
        parser.error("select --case-id or --all")

    service = get_evidence_retention_service()
    result = service.execute(
        mode=args.mode,
        case_id=None if args.all else args.case_id,
        require_review=bool(args.require_review),
        reviewed_by=args.reviewed_by,
        requested_by=args.requested_by,
        confirm_delete=args.confirm_delete,
    )
    result["all_cases"] = bool(args.all)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
