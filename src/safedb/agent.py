"""The agent loop: answer a question by driving the real MCP server over stdio.

This never imports executor.py directly — it starts ``safedb.server`` as a subprocess and
talks to it with the official MCP client, exactly as Claude Desktop / Cursor would, so the
eval measures what a real client experiences (safety layer included).

Loop: fetch the ``analyst`` prompt as the system message, send the question, and for each tool
call the model makes, forward it through the MCP client and append the result. Stop when the
model replies without a tool call or after ``MAX_TOOL_CALLS`` tool calls. The final SQL is the
last ``run_query`` that returned ``ok: true``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from safedb.llm_client import LLMClient

MAX_TOOL_CALLS = 5


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    ok: bool | None
    error_type: str | None


@dataclass
class AgentResult:
    final_sql: str | None = None
    final_columns: list[str] | None = None
    final_rows: list[list[Any]] | None = None
    answer: str | None = None
    steps: list[Step] = field(default_factory=list)
    tool_calls: int = 0
    blocked_count: int = 0
    first_try_valid: bool = False
    recovered: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    backend: str = ""
    model: str = ""
    reason: str | None = None


def _tool_schema(tool: Any) -> dict[str, Any]:
    return getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}


async def answer_question(
    llm: LLMClient,
    database: str,
    question: str,
    config_path: str = "config.yaml",
    on_request: Callable[[list[dict[str, Any]]], None] | None = None,
) -> AgentResult:
    """Run one benchmark question through the live MCP server and return what happened.

    ``on_request`` is called with the messages just before each model call (the eval uses it to
    assert the gold answer never leaks into a request).
    """
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "safedb.server", "--config", config_path],
        cwd=os.getcwd(),
        env=dict(os.environ),
    )
    result = AgentResult()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            neutral_tools = [
                {"name": t.name, "description": t.description, "input_schema": _tool_schema(t)}
                for t in tools
            ]
            prompt = await session.get_prompt("analyst", {"database": database})
            system = prompt.messages[0].content.text

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Database: {database}\n\nQuestion: {question}"},
            ]

            first_run_query_seen = False

            while True:
                if on_request is not None:
                    on_request(messages)
                llm_result = llm.generate(messages, tools=neutral_tools)
                result.tokens_in += llm_result.usage.input_tokens
                result.tokens_out += llm_result.usage.output_tokens
                result.latency_ms += llm_result.latency_ms
                result.backend = llm_result.backend
                result.model = llm_result.model

                if not llm_result.tool_calls:
                    result.answer = llm_result.text
                    break

                # Replay the assistant's tool_use blocks (ids preserved) ...
                assistant_content: list[dict[str, Any]] = []
                if llm_result.text:
                    assistant_content.append({"type": "text", "text": llm_result.text})
                for call in llm_result.tool_calls:
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                            "signature": call.signature,
                        }
                    )
                messages.append({"role": "assistant", "content": assistant_content})

                # ... then execute each call through the real server and return the results.
                tool_results: list[dict[str, Any]] = []
                hit_limit = False
                for call in llm_result.tool_calls:
                    result.tool_calls += 1
                    mcp_result = await session.call_tool(call.name, call.arguments)
                    content = mcp_result.structured_content or {}
                    ok = content.get("ok")
                    error_type = content.get("error_type")
                    result.steps.append(
                        Step(tool=call.name, args=call.arguments, ok=ok, error_type=error_type)
                    )

                    if call.name == "run_query":
                        if not first_run_query_seen:
                            first_run_query_seen = True
                            result.first_try_valid = ok is True
                        if error_type == "blocked":
                            result.blocked_count += 1
                        if ok is True:
                            result.final_sql = call.arguments.get("sql")
                            result.final_columns = content.get("columns")
                            result.final_rows = content.get("rows")

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": json.dumps(content),
                        }
                    )
                    if result.tool_calls >= MAX_TOOL_CALLS:
                        hit_limit = True
                        break

                messages.append({"role": "user", "content": tool_results})
                if hit_limit:
                    break

    if result.final_sql is None:
        result.reason = "no_successful_query"
    else:
        result.recovered = result.final_sql is not None and not result.first_try_valid
    return result
