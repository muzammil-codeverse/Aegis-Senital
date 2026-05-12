#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.env_loader import load_project_env
from app.db.schema_bootstrap import bootstrap_postgres_schema, iter_schema_statements, required_tables


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the Aegis Sentinel PostgreSQL schema.")
    parser.add_argument("--dsn", default=None, help="Override POSTGRES_DSN/AEGIS_POSTGRES_DSN/DB_URL.")
    parser.add_argument("--tables", nargs="*", default=None, help="Optional subset of tables to bootstrap.")
    parser.add_argument("--dry-run", action="store_true", help="Print the tables/statements that would be applied.")
    parser.add_argument("--apply", action="store_true", help="Apply schema changes.")
    args = parser.parse_args()

    load_project_env()
    table_names = list(args.tables or required_tables())

    if args.dry_run or not args.apply:
        payload = {
            "mode": "dry-run",
            "table_count": len(table_names),
            "tables": table_names,
            "statement_count": len(iter_schema_statements(table_names)),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    result = bootstrap_postgres_schema(args.dsn, table_names)
    result["mode"] = "apply"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("required_tables_ready", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
