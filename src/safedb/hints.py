"""Turn an ``unknown_object`` error into a helpful hint using difflib.

For an unknown column, suggest up to three closest real column names; for an unknown table,
suggest the closest table names and list the best match's columns. Hints are optional: the
server only calls this when ``HINTS=on`` (an eval experiment turns them off).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from safedb import db

_NO_TABLE = re.compile(r"no such table:\s*(\S+)", re.IGNORECASE)
_NO_COLUMN = re.compile(r"no such column:\s*(\S+)", re.IGNORECASE)


def _close(name: str, candidates: list[str]) -> list[str]:
    unique = sorted(set(candidates))
    return difflib.get_close_matches(name, unique, n=3, cutoff=0.5)


def hint_for_unknown_object(path: str | Path, message: str) -> str | None:
    """Build a hint for a 'no such table/column' message, or None if nothing matches."""
    table_match = _NO_TABLE.search(message)
    if table_match:
        bad = table_match.group(1)
        conn = db.open_readonly(path)
        try:
            tables = db.list_tables(conn)
            matches = _close(bad, tables)
            if not matches:
                return f"Unknown table {bad!r}. Available tables: {', '.join(tables)}"
            columns = [c["name"] for c in db.columns(conn, matches[0])]
            return (
                f"Unknown table {bad!r}. Did you mean: {', '.join(matches)}? "
                f"Columns of {matches[0]}: {', '.join(columns)}"
            )
        finally:
            conn.close()

    column_match = _NO_COLUMN.search(message)
    if column_match:
        bad = column_match.group(1)
        bad_name = bad.split(".")[-1]  # strip a table qualifier, e.g. Artist.Nme
        conn = db.open_readonly(path)
        try:
            all_columns = [c["name"] for t in db.list_tables(conn) for c in db.columns(conn, t)]
            matches = _close(bad_name, all_columns)
        finally:
            conn.close()
        if matches:
            return f"Unknown column {bad!r}. Did you mean: {', '.join(matches)}?"
        return f"Unknown column {bad!r}."

    return None
