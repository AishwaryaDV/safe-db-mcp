"""Query execution: the runtime walls behind the validator.

Even after validate_sql passes, execution adds independent protections: a read-only
connection, a SQLite authorizer (the second wall, in case a statement ever slips past the
parser), a wall-clock timeout via a progress handler, and row/cell caps. One fresh connection
per call, always closed.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from safedb import db, hints
from safedb.safety import QueryRejected, validate_sql

# Authorizer action codes that a read-only query legitimately needs. Everything else is denied.
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
}
for _name in ("SQLITE_RECURSIVE",):  # present on most builds; include when available
    _code = getattr(sqlite3, _name, None)
    if _code is not None:
        _ALLOWED_ACTIONS.add(_code)

_PROGRESS_STEPS = 1000  # check the clock roughly every 1000 VM instructions


class QueryResult(BaseModel):
    ok: bool
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    row_count: int | None = None
    truncated: bool | None = None
    elapsed_ms: int | None = None
    error_type: str | None = None
    message: str | None = None
    hint: str | None = None


class ExplainResult(BaseModel):
    ok: bool
    plan: list[str] | None = None
    error_type: str | None = None
    message: str | None = None
    hint: str | None = None


def read_only_authorizer(action: int, *_args: Any) -> int:
    """SQLite authorizer: allow only read actions, deny everything else."""
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _truncate_cell(value: Any, limit: int) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


def _classify(exc: sqlite3.Error, timed_out: bool) -> tuple[str, str]:
    """Map a SQLite error to (error_type, message)."""
    if timed_out:
        return "timeout", "query exceeded the time limit"
    text = str(exc).lower()
    if "no such table" in text or "no such column" in text:
        return "unknown_object", str(exc)
    if "syntax error" in text:
        return "syntax", str(exc)
    return "internal", "internal error"


def run_query(
    path: str | Path,
    sql: str,
    *,
    max_rows: int,
    max_rows_cap: int,
    timeout_s: float,
    max_cell_chars: int,
    max_sql_chars: int,
    hints_enabled: bool = False,
) -> QueryResult:
    """Validate and run a single read-only query, applying all runtime caps."""
    try:
        validate_sql(sql, max_sql_chars)
    except QueryRejected as rej:
        return QueryResult(ok=False, error_type=rej.error_type, message=rej.message)

    effective_max = min(max_rows, max_rows_cap)
    deadline = time.monotonic() + timeout_s
    timed_out = False

    def _progress() -> int:
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1  # non-zero aborts the current operation
        return 0

    conn = db.open_readonly(path)
    started = time.monotonic()
    try:
        conn.set_authorizer(read_only_authorizer)
        conn.set_progress_handler(_progress, _PROGRESS_STEPS)
        cursor = conn.execute(sql)
        fetched = cursor.fetchmany(effective_max + 1)
        truncated = len(fetched) > effective_max
        rows = [
            [_truncate_cell(value, max_cell_chars) for value in row]
            for row in fetched[:effective_max]
        ]
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return QueryResult(
            ok=True,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=elapsed_ms,
        )
    except sqlite3.Error as exc:
        error_type, message = _classify(exc, timed_out)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        hint = _hint_for(path, error_type, message, hints_enabled)
        return QueryResult(
            ok=False, error_type=error_type, message=message, hint=hint, elapsed_ms=elapsed_ms
        )
    finally:
        conn.set_progress_handler(None, _PROGRESS_STEPS)
        conn.close()


def _hint_for(path: str | Path, error_type: str, message: str, enabled: bool) -> str | None:
    """A difflib hint for unknown objects, only when hints are enabled."""
    if enabled and error_type == "unknown_object":
        return hints.hint_for_unknown_object(path, message)
    return None


def explain_query(
    path: str | Path,
    sql: str,
    *,
    max_sql_chars: int,
    timeout_s: float,
    hints_enabled: bool = False,
) -> ExplainResult:
    """Validate the SQL and return SQLite's query plan without executing the query."""
    try:
        validate_sql(sql, max_sql_chars)
    except QueryRejected as rej:
        return ExplainResult(ok=False, error_type=rej.error_type, message=rej.message)

    deadline = time.monotonic() + timeout_s
    timed_out = False

    def _progress() -> int:
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1
        return 0

    conn = db.open_readonly(path)
    try:
        conn.set_authorizer(read_only_authorizer)
        conn.set_progress_handler(_progress, _PROGRESS_STEPS)
        cursor = conn.execute(f"EXPLAIN QUERY PLAN {sql}")
        plan = [str(row[-1]) for row in cursor.fetchall()]
        return ExplainResult(ok=True, plan=plan)
    except sqlite3.Error as exc:
        error_type, message = _classify(exc, timed_out)
        hint = _hint_for(path, error_type, message, hints_enabled)
        return ExplainResult(ok=False, error_type=error_type, message=message, hint=hint)
    finally:
        conn.set_progress_handler(None, _PROGRESS_STEPS)
        conn.close()
