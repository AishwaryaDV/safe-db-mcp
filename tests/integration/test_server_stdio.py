"""Integration test: drive the server through the real MCP client over stdio.

This starts ``safedb.server`` as a subprocess and talks to it with the official MCP client,
so it exercises exactly what Claude Desktop / Cursor and the eval agent will experience.
Requires the Chinook database (``make setup`` or ``scripts/download_data.py``).
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO_ROOT = Path(__file__).resolve().parents[2]
CHINOOK = REPO_ROOT / "data" / "chinook" / "Chinook_Sqlite.sqlite"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not CHINOOK.exists(), reason="Chinook not downloaded; run make setup"),
]


@asynccontextmanager
async def connect():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "safedb.server", "--config", "config.yaml"],
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_lists_tools_resource_and_prompt():
    async with connect() as session:
        tools = await session.list_tools()
        assert {t.name for t in tools.tools} == {
            "list_databases",
            "describe_schema",
            "run_query",
            "explain_query",
        }

        prompts = await session.list_prompts()
        assert "analyst" in {p.name for p in prompts.prompts}

        templates = await session.list_resource_templates()
        assert "schema://{database}" in {t.uri_template for t in templates.resource_templates}


async def test_read_tools_return_chinook_data():
    async with connect() as session:
        dbs = await session.call_tool("list_databases", {})
        assert dbs.structured_content["databases"][0]["name"] == "chinook"
        assert dbs.structured_content["databases"][0]["table_count"] == 11

        artist = await session.call_tool(
            "describe_schema", {"database": "chinook", "table": "Artist"}
        )
        table = artist.structured_content["tables"][0]
        assert table["name"] == "Artist"
        assert table["row_count"] == 275
        assert len(table["sample_rows"]) == 3
        id_col = next(c for c in table["columns"] if c["name"] == "ArtistId")
        assert id_col["primary_key"] is True

        no_samples = await session.call_tool(
            "describe_schema", {"database": "chinook", "table": "Album", "sample_rows": 0}
        )
        assert no_samples.structured_content["tables"][0]["sample_rows"] is None


async def test_query_tools_registered_but_not_yet_enabled():
    async with connect() as session:
        result = await session.call_tool("run_query", {"database": "chinook", "sql": "SELECT 1"})
        assert result.structured_content["ok"] is False


async def test_resource_and_prompt_render():
    async with connect() as session:
        resource = await session.read_resource("schema://chinook")
        assert resource.contents[0].text.startswith("# Schema: chinook")

        prompt = await session.get_prompt("analyst", {"database": "chinook"})
        assert "chinook" in prompt.messages[0].content.text
