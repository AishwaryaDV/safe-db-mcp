"""Hostile-query validation tests (no database, no LLM).

These exercise validate_sql directly: the cases that must be rejected before any execution.
Execution-level cases (timeout, caps, unknown objects) live in test_execution.py.

Numbers in comments map to the hostile-query table in docs/PROJECT_A_BRIEF.md.
"""

import pytest

from safedb.safety import QueryRejected, validate_sql

BLOCKED = [
    "DROP TABLE Album",  # 1
    "DELETE FROM Album",  # 2
    "UPDATE Album SET Title = 'x'",  # 3
    "INSERT INTO Album (Title) VALUES ('x')",  # 4
    "CREATE TABLE t (x)",  # 5
    "ALTER TABLE Album ADD COLUMN c TEXT",  # 6
    "REPLACE INTO Album (Title) VALUES ('x')",  # 7
    "VACUUM",  # 8
    "SELECT 1; DROP TABLE Album",  # 9 (two statements)
    "SELECT 1; SELECT 2",  # 10 (two statements)
    "SELECT 1 /* ; */; DELETE FROM Album",  # 11
    "-- a comment\nDROP TABLE Album",  # 12
    "SeLeCt 1; dRoP table Album",  # 13
    "WITH t AS (SELECT 1) DELETE FROM Album",  # 14
    "PRAGMA table_info(Album)",  # 15
    "PRAGMA writable_schema = 1",  # 16
    "ATTACH DATABASE 'x.db' AS x",  # 17
    "SELECT load_extension('x')",  # 18
    "SELECT readfile('/etc/passwd')",  # 19
    "BEGIN",  # 33
    "COMMIT",  # 34
    "ROLLBACK",  # 35
    "SAVEPOINT s1",  # 36
    "RELEASE s1",  # 36
    "REINDEX",  # 37
    "ANALYZE",  # 38
    "DETACH DATABASE x",  # 39
    "SELECT ';' ; DROP TABLE Album",  # 40 (semicolon inside a string literal)
]

ALLOWED = [
    "SELECT * FROM sqlite_master",  # 20
    "WITH t AS (SELECT 1) SELECT * FROM t",
    "SELECT 1 UNION SELECT 2",
    "SELECT 1 EXCEPT SELECT 2",
    "SELECT count(*) FROM Track",
    "SELECT abs(-1)",
    "SELECT 1;",  # trailing semicolon is a single statement
]


@pytest.mark.safety
@pytest.mark.parametrize("sql", BLOCKED)
def test_blocked_queries(sql):
    with pytest.raises(QueryRejected) as excinfo:
        validate_sql(sql, max_sql_chars=4000)
    assert excinfo.value.error_type == "blocked"


@pytest.mark.safety
@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_queries(sql):
    # Should not raise; returns the parsed expression.
    assert validate_sql(sql, max_sql_chars=4000) is not None


@pytest.mark.safety
def test_too_large():  # 25
    with pytest.raises(QueryRejected) as excinfo:
        validate_sql("SELECT " + "1," * 5000 + "1", max_sql_chars=4000)
    assert excinfo.value.error_type == "too_large"


@pytest.mark.safety
@pytest.mark.parametrize("sql", ["", "   ", "SELEC * FROM Album"])  # 26, 27
def test_syntax_errors(sql):
    with pytest.raises(QueryRejected) as excinfo:
        validate_sql(sql, max_sql_chars=4000)
    assert excinfo.value.error_type == "syntax"
