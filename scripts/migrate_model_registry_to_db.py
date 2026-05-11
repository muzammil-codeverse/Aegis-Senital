from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.repositories.model_registry_repository import (  # noqa: E402
    FileModelRegistryRepository,
    PostgresModelRegistryRepository,
    flatten_registry_snapshot,
    get_model_registry_settings,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import models/registry.json into PostgreSQL model_registry_entries.")
    parser.add_argument("--file", default="models/registry.json", help="Source registry snapshot path")
    parser.add_argument("--apply", action="store_true", help="Write entries into PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Preview the migration without writing")
    args = parser.parse_args()

    settings = get_model_registry_settings()
    if not bool(settings.get("allow_file_to_db_migration", True)):
        print("Migration disabled by configs/runtime/model_registry.yaml")
        return 2

    source_repo = FileModelRegistryRepository(args.file)
    if not source_repo.is_available():
        print(f"Source registry unavailable: {source_repo.file_path}")
        return 2

    entries = source_repo.list_entries()
    grouped = source_repo.grouped_entries()
    print(f"Source backend: {source_repo.storage_backend}")
    print(f"Source file: {source_repo.file_path}")
    print(f"Entries: {len(entries)}")
    print(f"Model keys: {', '.join(sorted(grouped)) or '(none)'}")

    if args.dry_run or not args.apply:
        print("Dry run only. No database writes performed.")
        return 0

    target_repo = PostgresModelRegistryRepository(allow_writes=True)
    if not target_repo.is_available():
        health = target_repo.health_check().to_dict()
        print(f"Target PostgreSQL registry unavailable: {health.get('last_error')}")
        return 2

    inserted = target_repo.upsert_entries(entries)
    print(f"Migrated {inserted} entries into model_registry_entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
