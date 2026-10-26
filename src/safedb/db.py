"""Read-only SQLite access and schema introspection.

This module only runs fixed, parameterised introspection queries (``sqlite_master`` and
``PRAGMA``) against databases from the config registry. Model-written SQL never reaches here;
that goes through ``safety.py`` and ``executor.py`` (added in P2). Connections are opened
read-only so even introspection cannot mutate data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SAMPLE_CELL_LIMIT = 80  # describe_schema cuts sample cells longer than this


def _quote(identifier: str) -> str:
    """Quote a SQLite identifier, escaping embedded double quotes."""
    return '"' + identifier.replace('"', '""') + '"'


def open_readonly(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database read-only.

    Uses a ``file:`` URI with ``mode=ro``, sets ``PRAGMA query_only``, and disables extension
    loading. Raises FileNotFoundError if the file is missing.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"database file not found: {p}")
    conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    try:
        conn.enable_load_extension(False)
    except AttributeError:  # pragma: no cover - not all builds expose this
        pass
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    """User table names in alphabetical order (internal sqlite_* tables excluded)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def table_count(conn: sqlite3.Connection) -> int:
    return len(list_tables(conn))


def row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]


def columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """Columns via PRAGMA table_info: name, type, primary_key, not_null."""
    rows = conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    # table_info columns: cid, name, type, notnull, dflt_value, pk
    return [
        {"name": r[1], "type": r[2], "primary_key": bool(r[5]), "not_null": bool(r[3])}
        for r in rows
    ]


def foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """Foreign keys via PRAGMA foreign_key_list: column, ref_table, ref_column."""
    rows = conn.execute(f"PRAGMA foreign_key_list({_quote(table)})").fetchall()
    # foreign_key_list columns: id, seq, table, from, to, on_update, on_delete, match
    return [{"column": r[3], "ref_table": r[2], "ref_column": r[4]} for r in rows]


def sample_rows(
    conn: sqlite3.Connection, table: str, n: int, cell_limit: int = SAMPLE_CELL_LIMIT
) -> list[list[Any]]:
    """Up to ``n`` sample rows; string cells longer than ``cell_limit`` are ellipsised."""
    if n <= 0:
        return []
    cur = conn.execute(f"SELECT * FROM {_quote(table)} LIMIT ?", (n,))
    return [[_truncate_cell(value, cell_limit) for value in row] for row in cur.fetchall()]


def _truncate_cell(value: Any, limit: int) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value
