"""Audit log: a row for every tool call, including blocked and failed ones.

Writes go to a dedicated ``audit.sqlite`` file (separate from every data database) on their own
writable connection, so auditing never touches a read-only data connection and records even
calls that were rejected. The ``llm_calls`` table (shared conventions) is added in P5.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  source TEXT NOT NULL,
  tool TEXT NOT NULL,
  database TEXT,
  sql TEXT,
  sql_hash TEXT,
  status TEXT NOT NULL,
  error_type TEXT,
  reason TEXT,
  row_count INTEGER,
  truncated INTEGER,
  elapsed_ms INTEGER,
  run_id TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS audit_status ON audit_log (status);
"""


def init_db(path: str | Path) -> None:
    """Create the audit database and schema if they do not exist."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def write_audit(
    path: str | Path,
    *,
    source: str,
    tool: str,
    status: str,
    database: str | None = None,
    sql: str | None = None,
    error_type: str | None = None,
    reason: str | None = None,
    row_count: int | None = None,
    truncated: bool | None = None,
    elapsed_ms: int | None = None,
    run_id: str | None = None,
) -> None:
    """Append one audit row on a fresh writable connection."""
    sql_hash = hashlib.sha256(sql.encode()).hexdigest() if sql is not None else None
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            INSERT INTO audit_log
              (ts, source, tool, database, sql, sql_hash, status, error_type, reason,
               row_count, truncated, elapsed_ms, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                source,
                tool,
                database,
                sql,
                sql_hash,
                status,
                error_type,
                reason,
                row_count,
                None if truncated is None else int(truncated),
                elapsed_ms,
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
