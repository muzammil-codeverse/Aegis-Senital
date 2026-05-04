"""
Legacy database module — schema conflict resolved.

The duplicate Event/Detection SQLAlchemy models that conflicted with the
PostgresManager DDL (inference/db/postgres_manager.py) have been removed.
All schema management is now owned by PostgresManager.
"""


def init_db() -> None:
    """No-op. Schema is fully managed by PostgresManager DDL at startup."""
