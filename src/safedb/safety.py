"""SQL validation: the first wall in front of model-written SQL.

``validate_sql`` parses with sqlglot (SQLite dialect) and allows exactly one read-only
statement. It is pure (no database access); the executor adds the runtime walls (read-only
connection, authorizer, timeout, row/cell caps). Behaviour was confirmed against sqlglot
30.25.0: dangerous calls parse as ``exp.Anonymous`` (name = function), set operations are
``Union``/``Except``/``Intersect``, and empty input parses to ``[None]``.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# A validated query's root must be one of these read-only shapes.
ALLOWED_ROOTS: tuple[type[exp.Expression], ...] = (
    exp.Select,
    exp.Union,
    exp.Intersect,
    exp.Except,
)

# Any of these appearing anywhere in the tree rejects the query (defence in depth behind the
# root check, to catch write operations nested in CTEs or subqueries).
DENIED_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,  # VACUUM, REPLACE, and other statements sqlglot cannot model
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Transaction,  # BEGIN
    exp.Commit,
    exp.Rollback,
    exp.Analyze,
)

# Functions denied by name (SQLite can expose file/extension access through these).
DANGEROUS_FUNCTIONS: frozenset[str] = frozenset(
    {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}
)


class QueryRejected(Exception):
    """Raised when a query fails validation. ``error_type`` is one of the tool error types."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def validate_sql(sql: str, max_sql_chars: int) -> exp.Expression:
    """Validate a single read-only SQL statement. Returns the parsed root or raises.

    error_type is ``too_large``, ``syntax``, or ``blocked``.
    """
    if len(sql) > max_sql_chars:
        raise QueryRejected("too_large", f"SQL is longer than {max_sql_chars} characters")

    try:
        parsed = sqlglot.parse(sql, dialect="sqlite", error_level=sqlglot.ErrorLevel.RAISE)
    except ParseError as exc:
        raise QueryRejected("syntax", str(exc).splitlines()[0]) from exc

    statements = [stmt for stmt in parsed if stmt is not None]
    if not statements:
        raise QueryRejected("syntax", "empty query")
    if len(statements) > 1:
        raise QueryRejected("blocked", "only one SELECT statement is allowed")

    root = statements[0]
    if not isinstance(root, ALLOWED_ROOTS):
        raise QueryRejected("blocked", "only one read-only SELECT statement is allowed")

    for node in root.walk():
        if isinstance(node, DENIED_NODES):
            raise QueryRejected("blocked", "only read-only SELECT statements are allowed")
        if isinstance(node, exp.Anonymous) and node.name.lower() in DANGEROUS_FUNCTIONS:
            raise QueryRejected("blocked", f"function {node.name!r} is not allowed")

    return root
