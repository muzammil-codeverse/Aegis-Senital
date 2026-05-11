from __future__ import annotations

from app.db.schema_bootstrap import bootstrap_schema, iter_schema_statements, verify_required_tables


class _FakeCursor:
    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self._connection.executed.append((statement.strip(), params))

    def fetchall(self):
        return list(self._connection.fetchall_rows)


class _FakeConnection:
    def __init__(self, rows=None):
        self.executed = []
        self.fetchall_rows = rows or []
        self.commit_count = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_count += 1


def test_schema_statements_include_required_tables():
    statements = iter_schema_statements(("cases", "case_evidence", "case_audit_logs"))
    assert any("CREATE TABLE IF NOT EXISTS cases" in statement for statement in statements)
    assert any("CREATE TABLE IF NOT EXISTS case_evidence" in statement for statement in statements)
    assert any("CREATE OR REPLACE VIEW case_audit" in statement for statement in statements)


def test_schema_bootstrap_is_idempotent():
    connection = _FakeConnection()
    first = bootstrap_schema(connection, ("cases", "case_evidence"))
    second = bootstrap_schema(connection, ("cases", "case_evidence"))

    assert len(first) == len(second)
    assert connection.commit_count == 2


def test_verify_required_tables_reports_missing_entries():
    connection = _FakeConnection(rows=[("cases",), ("case_evidence",)])
    status = verify_required_tables(connection, ("cases", "case_evidence", "case_reports"))

    assert status["cases"] is True
    assert status["case_evidence"] is True
    assert status["case_reports"] is False
