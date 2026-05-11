from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable

from app.core.persistence import postgres_dsn
from app.db.schema_definitions import COMPATIBILITY_STATEMENTS, REQUIRED_TABLES, TABLE_DEFINITIONS

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency in some test environments
    psycopg2 = None


def required_tables() -> list[str]:
    return list(REQUIRED_TABLES)


def iter_schema_statements(table_names: Iterable[str] | None = None) -> list[str]:
    names = list(table_names or TABLE_DEFINITIONS.keys())
    statements: list[str] = []
    for table_name in names:
        definition = TABLE_DEFINITIONS[table_name]
        statements.append(str(definition["ddl"]).strip())
        statements.extend(str(item).strip() for item in definition.get("alters", ()))
        statements.extend(str(item).strip() for item in definition.get("indexes", ()))
    if set(names) >= {"case_audit_logs"}:
        statements.extend(statement.strip() for statement in COMPATIBILITY_STATEMENTS)
    return [statement for statement in statements if statement]


def bootstrap_schema(connection: Any, table_names: Iterable[str] | None = None) -> list[str]:
    statements = iter_schema_statements(table_names)
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    if hasattr(connection, "commit"):
        connection.commit()
    return statements


def verify_required_tables(connection: Any, table_names: Iterable[str] | None = None) -> dict[str, bool]:
    required = list(table_names or REQUIRED_TABLES)
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    available = {str(row[0] if isinstance(row, (list, tuple)) else row.get("table_name")) for row in rows}
    return {table_name: table_name in available for table_name in required}


@contextmanager
def connect_postgres(dsn: str | None = None):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")
    resolved_dsn = dsn or postgres_dsn()
    if not resolved_dsn:
        raise RuntimeError("POSTGRES_DSN is not configured")
    connection = psycopg2.connect(resolved_dsn, connect_timeout=5)
    try:
        yield connection
    finally:
        connection.close()


def bootstrap_postgres_schema(dsn: str | None = None, table_names: Iterable[str] | None = None) -> dict[str, Any]:
    with connect_postgres(dsn) as connection:
        executed = bootstrap_schema(connection, table_names)
        tables = verify_required_tables(connection, table_names)
    return {
        "executed_statements": len(executed),
        "tables": tables,
        "required_tables_ready": all(tables.values()) if tables else True,
    }
