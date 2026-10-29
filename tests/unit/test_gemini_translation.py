"""Neutral -> Gemini translation (no network, no key)."""

import pytest

from safedb.llm_client import gemini_contents, gemini_tools


@pytest.mark.unit
def test_gemini_tools_builds_function_declarations():
    tools = [{"name": "run_query", "description": "run it", "input_schema": {"type": "object"}}]
    out = gemini_tools(tools)
    assert len(out) == 1
    decls = out[0].function_declarations
    assert decls[0].name == "run_query"
    assert gemini_tools(None) is None


@pytest.mark.unit
def test_gemini_contents_maps_roles_and_tool_calls():
    messages = [
        {"role": "system", "content": "you are an analyst"},
        {"role": "user", "content": "how many tracks?"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "run_query", "input": {"sql": "SELECT 1"}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"ok": true}'}],
        },
    ]
    system, contents = gemini_contents(messages)
    assert system == "you are an analyst"
    assert [c.role for c in contents] == ["user", "model", "user"]
    # the assistant turn carries a function_call for run_query
    assert contents[1].parts[0].function_call.name == "run_query"
    # the tool result is mapped to a function_response for the same tool name (via id -> name)
    assert contents[2].parts[0].function_response.name == "run_query"
