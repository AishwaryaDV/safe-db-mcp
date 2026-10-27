"""The MCP server: four tools, one resource, one prompt, over stdio.

Read tools (``list_databases``, ``describe_schema``) are fully implemented here. The two
query tools (``run_query``, ``explain_query``) are registered so clients can discover them,
but return a clear "not yet enabled" error until the safety layer lands in P2 — no
model-written SQL is executed before then.

Confirmed against mcp 2.3.0: ``from mcp.server.mcpserver import MCPServer`` with
``@mcp.tool`` / ``@mcp.resource`` / ``@mcp.prompt`` decorators and ``mcp.run("stdio")``.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from safedb import __version__, audit, db, executor
from safedb.config import AppConfig, load_config
from safedb.tool_descriptions import TOOL_DESCRIPTIONS

# --- Tool output models ------------------------------------------------------


class DatabaseInfo(BaseModel):
    name: str
    description: str
    table_count: int


class DatabasesList(BaseModel):
    databases: list[DatabaseInfo]


class ColumnInfo(BaseModel):
    name: str
    type: str
    primary_key: bool
    not_null: bool


class ForeignKeyInfo(BaseModel):
    column: str
    ref_table: str
    ref_column: str


class TableInfo(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo]
    sample_rows: list[list[Any]] | None = None


class SchemaResult(BaseModel):
    database: str
    tables: list[TableInfo]


# --- Server construction -----------------------------------------------------

ANALYST_PROMPT = (
    "You are a careful data analyst querying database '{database}' through read-only tools.\n"
    "- Call describe_schema before writing SQL so you use real table and column names.\n"
    "- Quote identifiers that need it.\n"
    "- Always limit the number of rows you request.\n"
    "- State any assumptions you make in your answer.\n"
    "- If the question is ambiguous, ask one clarifying question instead of guessing.\n"
    "- Never attempt to change data; these tools are read-only."
)


def _clamp_sample_rows(value: int | None, default: int) -> int:
    n = default if value is None else value
    return max(0, min(5, n))


def _status_for(ok: bool, error_type: str | None) -> str:
    """Map a result to an audit status (ok | blocked | timeout | error)."""
    if ok:
        return "ok"
    if error_type in ("blocked", "timeout"):
        return error_type
    return "error"


@contextmanager
def _audit_call(
    config: AppConfig,
    tool: str,
    *,
    source: str = "mcp",
    database: str | None = None,
    sql: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Record exactly one audit row for a tool call, including on exception.

    The body may update the yielded dict (status, error_type, row_count, ...); the row is
    written in a finally so blocked and failed calls are logged too.
    """
    rec: dict[str, Any] = {
        "status": "ok",
        "error_type": None,
        "reason": None,
        "row_count": None,
        "truncated": None,
        "elapsed_ms": None,
    }
    try:
        yield rec
    except Exception as exc:
        rec["status"] = "error"
        rec["reason"] = str(exc)
        raise
    finally:
        audit.write_audit(
            config.audit_db, source=source, tool=tool, database=database, sql=sql, **rec
        )


def build_server(config: AppConfig) -> MCPServer:
    """Build the MCP server bound to a given config."""
    audit.init_db(config.audit_db)
    mcp = MCPServer("safe-db-mcp", version=__version__)

    @mcp.tool(name="list_databases", description=TOOL_DESCRIPTIONS["list_databases"])
    def list_databases() -> DatabasesList:
        with _audit_call(config, "list_databases"):
            infos: list[DatabaseInfo] = []
            for entry in config.databases:
                conn = db.open_readonly(entry.path)
                try:
                    count = db.table_count(conn)
                finally:
                    conn.close()
                infos.append(
                    DatabaseInfo(name=entry.name, description=entry.description, table_count=count)
                )
            return DatabasesList(databases=infos)

    @mcp.tool(name="describe_schema", description=TOOL_DESCRIPTIONS["describe_schema"])
    def describe_schema(
        database: str, table: str | None = None, sample_rows: int | None = None
    ) -> SchemaResult:
        with _audit_call(config, "describe_schema", database=database):
            entry = config.database(database)  # raises KeyError with known names if unknown
            n_samples = _clamp_sample_rows(sample_rows, config.limits.sample_rows_default)
            conn = db.open_readonly(entry.path)
            try:
                available = db.list_tables(conn)
                if table is not None:
                    if table not in available:
                        known = ", ".join(available)
                        raise ValueError(f"unknown table {table!r}; tables: {known}")
                    targets = [table]
                else:
                    targets = available

                tables = [
                    TableInfo(
                        name=name,
                        row_count=db.row_count(conn, name),
                        columns=[ColumnInfo(**c) for c in db.columns(conn, name)],
                        foreign_keys=[ForeignKeyInfo(**fk) for fk in db.foreign_keys(conn, name)],
                        sample_rows=db.sample_rows(conn, name, n_samples) if n_samples else None,
                    )
                    for name in targets
                ]
            finally:
                conn.close()
            return SchemaResult(database=database, tables=tables)

    @mcp.tool(name="run_query", description=TOOL_DESCRIPTIONS["run_query"])
    def run_query(database: str, sql: str, max_rows: int | None = None) -> executor.QueryResult:
        with _audit_call(config, "run_query", database=database, sql=sql) as rec:
            try:
                entry = config.database(database)
            except KeyError as exc:
                result = executor.QueryResult(
                    ok=False, error_type="unknown_object", message=str(exc)
                )
            else:
                limits = config.limits
                rows = limits.max_rows_default if max_rows is None else max_rows
                result = executor.run_query(
                    entry.path,
                    sql,
                    max_rows=rows,
                    max_rows_cap=limits.max_rows_cap,
                    timeout_s=limits.timeout_s,
                    max_cell_chars=limits.max_cell_chars,
                    max_sql_chars=limits.max_sql_chars,
                )
            rec["status"] = _status_for(result.ok, result.error_type)
            rec["error_type"] = result.error_type
            rec["row_count"] = result.row_count
            rec["truncated"] = result.truncated
            rec["elapsed_ms"] = result.elapsed_ms
            return result

    @mcp.tool(name="explain_query", description=TOOL_DESCRIPTIONS["explain_query"])
    def explain_query(database: str, sql: str) -> executor.ExplainResult:
        with _audit_call(config, "explain_query", database=database, sql=sql) as rec:
            try:
                entry = config.database(database)
            except KeyError as exc:
                result = executor.ExplainResult(
                    ok=False, error_type="unknown_object", message=str(exc)
                )
            else:
                limits = config.limits
                result = executor.explain_query(
                    entry.path,
                    sql,
                    max_sql_chars=limits.max_sql_chars,
                    timeout_s=limits.timeout_s,
                )
            rec["status"] = _status_for(result.ok, result.error_type)
            rec["error_type"] = result.error_type
            return result

    @mcp.resource("schema://{database}")
    def schema_resource(database: str) -> str:
        return _schema_markdown(config, database)

    @mcp.prompt(name="analyst")
    def analyst(database: str) -> str:
        return ANALYST_PROMPT.format(database=database)

    return mcp


def _schema_markdown(config: AppConfig, database: str) -> str:
    """Render a database's full schema as markdown, for clients that attach resources."""
    entry = config.database(database)
    conn = db.open_readonly(entry.path)
    try:
        lines = [f"# Schema: {database}", ""]
        for name in db.list_tables(conn):
            lines.append(f"## {name} ({db.row_count(conn, name)} rows)")
            lines.append("")
            lines.append("| column | type | pk | not null |")
            lines.append("| --- | --- | --- | --- |")
            for c in db.columns(conn, name):
                pk = "yes" if c["primary_key"] else ""
                nn = "yes" if c["not_null"] else ""
                lines.append(f"| {c['name']} | {c['type']} | {pk} | {nn} |")
            fks = db.foreign_keys(conn, name)
            if fks:
                lines.append("")
                for fk in fks:
                    lines.append(f"- FK: {fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")
            lines.append("")
    finally:
        conn.close()
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="safedb-mcp", description="Safe SQLite MCP server")
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    build_server(config).run(transport="stdio")


if __name__ == "__main__":
    main()
