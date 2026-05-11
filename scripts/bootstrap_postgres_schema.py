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

from app.db.schema_bootstrap import bootstrap_postgres_schema, required_tables


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the Aegis Sentinel PostgreSQL schema.")
    parser.add_argument("--dsn", default=None, help="Override POSTGRES_DSN/AEGIS_POSTGRES_DSN/DB_URL.")
    parser.add_argument(
        "--tables",
        nargs="*",
        default=None,
        help="Optional subset of tables to bootstrap. Defaults to the required Phase 37 set.",
    )
    args = parser.parse_args()

    result = bootstrap_postgres_schema(args.dsn, args.tables or required_tables())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("required_tables_ready", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
