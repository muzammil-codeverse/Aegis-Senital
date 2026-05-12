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
from app.db.schema_bootstrap import connect_postgres, required_tables, verify_required_tables


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the Aegis Sentinel PostgreSQL schema.")
    parser.add_argument("--dsn", default=None, help="Override POSTGRES_DSN/AEGIS_POSTGRES_DSN/DB_URL.")
    parser.add_argument("--tables", nargs="*", default=None, help="Optional subset of tables to verify.")
    args = parser.parse_args()

    load_project_env()
    table_names = list(args.tables or required_tables())
    with connect_postgres(args.dsn) as connection:
        table_status = verify_required_tables(connection, table_names)

    missing_tables = sorted(name for name, present in table_status.items() if not present)
    payload = {
        "required_tables_ready": not missing_tables,
        "table_count": len(table_names),
        "tables": table_status,
        "missing_tables": missing_tables,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not missing_tables else 1


if __name__ == "__main__":
    raise SystemExit(main())
