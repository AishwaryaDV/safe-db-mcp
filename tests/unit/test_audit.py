import sqlite3

import pytest

from safedb import audit


@pytest.mark.unit
def test_init_creates_schema(tmp_path):
    path = tmp_path / "audit.sqlite"
    audit.init_db(path)
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "audit_log" in tables
    conn.close()


@pytest.mark.unit
def test_write_audit_row(tmp_path):
    path = tmp_path / "audit.sqlite"
    audit.init_db(path)
    audit.write_audit(
        path,
        source="mcp",
        tool="run_query",
        database="chinook",
        sql="SELECT 1",
        status="ok",
        row_count=1,
        truncated=False,
        elapsed_ms=5,
    )
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT source, tool, database, sql, sql_hash, status, truncated FROM audit_log"
    ).fetchone()
    conn.close()
    assert row[0] == "mcp"
    assert row[1] == "run_query"
    assert row[2] == "chinook"
    assert row[3] == "SELECT 1"
    assert len(row[4]) == 64  # sha256 hex of the sql
    assert row[5] == "ok"
    assert row[6] == 0  # truncated stored as int
