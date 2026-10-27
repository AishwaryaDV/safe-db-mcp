"""The authorizer is an independent second wall: it must deny writes even when validate_sql
is bypassed and the connection is writable."""

import sqlite3

import pytest

from safedb.executor import read_only_authorizer


@pytest.fixture
def writable_db(tmp_path):
    path = tmp_path / "w.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t (x) VALUES (1)")
    conn.commit()
    conn.close()
    return path


@pytest.mark.safety
def test_authorizer_denies_write_on_writable_connection(writable_db):
    conn = sqlite3.connect(writable_db)  # deliberately writable; no validate_sql in front
    conn.set_authorizer(read_only_authorizer)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("INSERT INTO t (x) VALUES (2)")
    conn.close()


@pytest.mark.safety
def test_authorizer_allows_select(writable_db):
    conn = sqlite3.connect(writable_db)
    conn.set_authorizer(read_only_authorizer)
    assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
    conn.close()
