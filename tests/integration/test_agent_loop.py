"""The agent loop drives the real MCP server end-to-end (scripted model, no network)."""

from pathlib import Path

import pytest

from safedb.agent import answer_question
from safedb.config import Settings
from safedb.llm_client import LLMClient, ToolCall, Usage

CHINOOK = Path(__file__).resolve().parents[2] / "data" / "chinook" / "Chinook_Sqlite.sqlite"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not CHINOOK.exists(), reason="Chinook not downloaded; run make setup"),
]


class ScriptedBackend:
    """Turn 1: call run_query. Turn 2 (after the result): give a final answer."""

    name = "claude_sdk"
    default_model = "claude-sonnet-5"

    def __init__(self):
        self.turn = 0

    def generate(self, model, messages, tools, response_schema, temperature):
        self.turn += 1
        if self.turn == 1:
            call = ToolCall(
                id="t1",
                name="run_query",
                arguments={"database": "chinook", "sql": "SELECT COUNT(*) FROM Track"},
            )
            return (None, [call], Usage(input_tokens=100, output_tokens=20))
        return ("There are many tracks.", [], Usage(input_tokens=120, output_tokens=10))


async def test_agent_answers_through_real_server(tmp_path):
    llm = LLMClient(
        Settings(llm_backend="claude_sdk", llm_mode="record", daily_llm_budget=200),
        db_path=tmp_path / "audit.sqlite",
        cache_dir=tmp_path / "llm_cache",
        backend=ScriptedBackend(),
    )

    result = await answer_question(llm, "chinook", "How many tracks are there?")

    assert result.final_sql == "SELECT COUNT(*) FROM Track"
    assert result.final_rows is not None and result.final_rows[0][0] > 1000
    assert result.answer.startswith("There are")
    assert result.tool_calls == 1
    assert result.first_try_valid is True
    assert result.reason is None
    assert len(result.steps) == 1
    assert result.steps[0].tool == "run_query"
    assert result.steps[0].ok is True


async def test_agent_reports_no_successful_query(tmp_path):
    class AlwaysBlocked:
        name = "claude_sdk"
        default_model = "claude-sonnet-5"

        def __init__(self):
            self.turn = 0

        def generate(self, model, messages, tools, response_schema, temperature):
            self.turn += 1
            if self.turn == 1:
                call = ToolCall(
                    id="t1",
                    name="run_query",
                    arguments={"database": "chinook", "sql": "DROP TABLE Album"},
                )
                return (None, [call], Usage())
            return ("I could not answer that.", [], Usage())

    llm = LLMClient(
        Settings(llm_backend="claude_sdk", llm_mode="record", daily_llm_budget=200),
        db_path=tmp_path / "audit.sqlite",
        cache_dir=tmp_path / "llm_cache",
        backend=AlwaysBlocked(),
    )

    result = await answer_question(llm, "chinook", "Delete the albums")
    assert result.final_sql is None
    assert result.reason == "no_successful_query"
    assert result.blocked_count == 1
