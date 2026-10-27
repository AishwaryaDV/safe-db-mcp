"""Every tool call — ok, blocked, or failed — must write exactly one audit row."""

import sqlite3
from pathlib import Path

import pytest

from safedb.config import AppConfig, DatabaseConfig, Limits
from safedb.server import build_server

CHINOOK = Path(__file__).resolve().parents[2] / "data" / "chinook" / "Chinook_Sqlite.sqlite"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not CHINOOK.exists(), reason="Chinook not downloaded; run make setup"),
]


async def test_every_tool_call_writes_one_audit_row(tmp_path):
    audit_db = tmp_path / "audit.sqlite"
    config = AppConfig(
        databases=[DatabaseConfig(name="chinook", path=str(CHINOOK), description="x")],
        limits=Limits(),
        audit_db=str(audit_db),
    )
    mcp = build_server(config)

    await mcp.call_tool("list_databases", {})
    await mcp.call_tool("describe_schema", {"database": "chinook", "table": "Artist"})
    await mcp.call_tool("run_query", {"database": "chinook", "sql": "SELECT 1"})
    await mcp.call_tool("run_query", {"database": "chinook", "sql": "DROP TABLE Album"})

    conn = sqlite3.connect(audit_db)
    rows = conn.execute("SELECT tool, status, error_type FROM audit_log ORDER BY id").fetchall()
    conn.close()

    assert [r[0] for r in rows] == [
        "list_databases",
        "describe_schema",
        "run_query",
        "run_query",
    ]
    # the blocked DROP is logged with status + error_type "blocked"
    assert rows[3][1] == "blocked"
    assert rows[3][2] == "blocked"


async def test_unknown_database_returns_hint_listing_real_names(tmp_path):  # 30
    config = AppConfig(
        databases=[DatabaseConfig(name="chinook", path=str(CHINOOK), description="x")],
        limits=Limits(),
        audit_db=str(tmp_path / "audit.sqlite"),
    )
    mcp = build_server(config)
    result = await mcp.call_tool("run_query", {"database": "nope", "sql": "SELECT 1"})
    content = result.structured_content
    assert content["error_type"] == "unknown_object"
    assert content["hint"] and "chinook" in content["hint"]
