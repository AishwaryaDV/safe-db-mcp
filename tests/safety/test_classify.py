"""Unit tests for the SQLite error classifier (no database needed)."""

import sqlite3

import pytest

from safedb.executor import _classify


@pytest.mark.safety
def test_timeout_takes_precedence():
    assert _classify(sqlite3.OperationalError("interrupted"), timed_out=True)[0] == "timeout"


@pytest.mark.safety
def test_unknown_object():
    assert _classify(sqlite3.OperationalError("no such column: Nme"), False)[0] == "unknown_object"
    assert _classify(sqlite3.OperationalError("no such table: X"), False)[0] == "unknown_object"


@pytest.mark.safety
def test_syntax():
    assert _classify(sqlite3.OperationalError('near "x": syntax error'), False)[0] == "syntax"


@pytest.mark.safety
def test_internal_is_generic():
    error_type, message = _classify(sqlite3.OperationalError("database is locked"), False)
    assert error_type == "internal"
    assert message == "internal error"  # no internal detail leaked
