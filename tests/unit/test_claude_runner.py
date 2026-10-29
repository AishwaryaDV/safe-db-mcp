"""Fold Agent SDK blocks into an AgentResult (pure, no model, no tokens)."""

import pytest
from claude_agent_sdk import ToolResultBlock, ToolUseBlock
from eval.claude_runner import build_result_from_blocks


def _tool_use(block_id, tool, args):
    return ToolUseBlock(id=block_id, name=f"mcp__safedb__{tool}", input=args)


def _tool_result(block_id, payload):
    import json

    return ToolResultBlock(tool_use_id=block_id, content=json.dumps(payload), is_error=False)


@pytest.mark.unit
def test_successful_question():
    blocks = [
        _tool_use("1", "describe_schema", {"database": "chinook"}),
        _tool_result("1", {"tables": []}),
        _tool_use("2", "run_query", {"database": "chinook", "sql": "SELECT 1 AS n"}),
        _tool_result("2", {"ok": True, "rows": [[1]], "columns": ["n"]}),
    ]
    result = build_result_from_blocks(
        blocks,
        answer="The answer is 1.",
        usage={"input_tokens": 50, "output_tokens": 8},
        model="claude-sonnet-5",
        latency_ms=1200,
    )
    assert result.tool_calls == 2
    assert result.final_sql == "SELECT 1 AS n"
    assert result.final_rows == [[1]]
    assert result.first_try_valid is True
    assert result.reason is None
    assert result.tokens_in == 50
    assert result.backend == "claude_sdk"
    assert [s.tool for s in result.steps] == ["describe_schema", "run_query"]


@pytest.mark.unit
def test_blocked_question_reports_no_successful_query():
    blocks = [
        _tool_use("1", "run_query", {"database": "chinook", "sql": "DROP TABLE Album"}),
        _tool_result("1", {"ok": False, "error_type": "blocked"}),
    ]
    result = build_result_from_blocks(
        blocks, answer="can't", usage=None, model="sonnet", latency_ms=10
    )
    assert result.final_sql is None
    assert result.blocked_count == 1
    assert result.first_try_valid is False
    assert result.reason == "no_successful_query"


@pytest.mark.unit
def test_recovery_flag():
    blocks = [
        _tool_use("1", "run_query", {"database": "x", "sql": "SELECT Nme FROM Artist"}),
        _tool_result("1", {"ok": False, "error_type": "unknown_object"}),
        _tool_use("2", "run_query", {"database": "x", "sql": "SELECT Name FROM Artist"}),
        _tool_result("2", {"ok": True, "rows": [["AC/DC"]], "columns": ["Name"]}),
    ]
    result = build_result_from_blocks(
        blocks, answer="ok", usage=None, model="sonnet", latency_ms=10
    )
    assert result.first_try_valid is False
    assert result.final_sql == "SELECT Name FROM Artist"
    assert result.recovered is True
