"""Hints for unknown objects (tests 28-30), and that HINTS=off returns message only."""

from pathlib import Path

import pytest

from safedb.executor import run_query

CHINOOK = Path(__file__).resolve().parents[2] / "data" / "chinook" / "Chinook_Sqlite.sqlite"

pytestmark = [
    pytest.mark.safety,
    pytest.mark.skipif(not CHINOOK.exists(), reason="Chinook not downloaded; run make setup"),
]

DEFAULTS = dict(
    max_rows=100, max_rows_cap=1000, timeout_s=3, max_cell_chars=500, max_sql_chars=4000
)


def run(sql: str, **over):
    return run_query(CHINOOK, sql, **{**DEFAULTS, **over})


def test_unknown_column_hint_suggests_name():  # 28
    result = run("SELECT Nme FROM Artist", hints_enabled=True)
    assert result.error_type == "unknown_object"
    assert result.hint is not None and "Name" in result.hint


def test_unknown_table_hint_suggests_album():  # 29
    result = run("SELECT * FROM Albums", hints_enabled=True)
    assert result.error_type == "unknown_object"
    assert result.hint is not None and "Album" in result.hint


def test_hints_off_returns_message_only():
    result = run("SELECT Nme FROM Artist", hints_enabled=False)
    assert result.error_type == "unknown_object"
    assert result.message is not None
    assert result.hint is None
