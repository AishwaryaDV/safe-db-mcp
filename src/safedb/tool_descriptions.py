"""Model-facing tool descriptions, kept in one place.

Wording changes affect accuracy, so every eval run records a hash of this file
(``descriptions_hash``). Each description is at most three sentences and says when to use the
tool.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

LIST_DATABASES = (
    "List the databases available to query, with a short description and table count for each. "
    "Call this first to discover what you can query."
)

DESCRIBE_SCHEMA = (
    "Return the tables, columns, keys, and a few sample rows for a database. "
    "Call this before writing SQL so you use real table and column names. "
    "Pass a table to inspect just one, or sample_rows=0 to omit the samples."
)

RUN_QUERY = (
    "Run a single read-only SELECT against a database and get the rows back. "
    "The query is rejected if it is not one read-only statement, and results are capped and "
    "may be truncated. Call describe_schema first to get exact table and column names."
)

EXPLAIN_QUERY = (
    "Return SQLite's query plan for a SELECT without executing it. "
    "Use it to check how a query will run or to debug a slow one. "
    "The same validation as run_query applies."
)

TOOL_DESCRIPTIONS = {
    "list_databases": LIST_DATABASES,
    "describe_schema": DESCRIBE_SCHEMA,
    "run_query": RUN_QUERY,
    "explain_query": EXPLAIN_QUERY,
}


def descriptions_hash() -> str:
    """SHA-256 of this file's source, recorded in every eval run."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
