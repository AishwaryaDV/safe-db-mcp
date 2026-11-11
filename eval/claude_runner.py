"""Claude eval path: let the Claude Agent SDK run a whole question against the MCP server.

Unlike the Gemini path (our per-turn agent loop in safedb.agent), the Claude Agent SDK runs
its own loop — it connects to the safe-db-mcp server over stdio and calls the read-only tools
itself, on the owner's Claude Code login (Sonnet, no API key). We watch the messages it emits
and fold them into the same AgentResult the Gemini path produces, so both score identically.

Replay is question-level: a recorded run's AgentResult is cached under llm_cache/claude/ and
replayed verbatim (CI and keyless runs cost nothing). Validated end-to-end on the first record
run (deferred to avoid spending subscription tokens mid-session).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from safedb.agent import AgentResult, Step
from safedb.llm_client import CacheMiss
from safedb.server import ANALYST_PROMPT

MCP_SERVER_NAME = "safedb"
TOOL_PREFIX = f"mcp__{MCP_SERVER_NAME}__"
TOOLS = ["list_databases", "describe_schema", "run_query", "explain_query"]
ALLOWED_TOOLS = [f"{TOOL_PREFIX}{t}" for t in TOOLS]
DEFAULT_MODEL = "sonnet"
MAX_TURNS = 12
MAX_BUDGET_USD = 0.5  # native per-question cost cap (token safety net)


def _parse_result_content(content: Any) -> dict[str, Any]:
    """A tool result's content may be a JSON string or a list of text blocks; parse to a dict."""
    if isinstance(content, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else getattr(part, "text", "")
            for part in content
        )
    else:
        text = content if isinstance(content, str) else str(content)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def build_result_from_blocks(
    blocks: list[Any],
    answer: str | None,
    usage: dict[str, Any] | None,
    model: str,
    latency_ms: int,
) -> AgentResult:
    """Fold a flat list of Agent SDK content blocks into our AgentResult (pure, testable)."""
    from claude_agent_sdk import ToolResultBlock, ToolUseBlock

    result = AgentResult(answer=answer, backend="claude_sdk", model=model, latency_ms=latency_ms)
    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    first_run_query_seen = False

    for block in blocks:
        if isinstance(block, ToolUseBlock):
            name = block.name.removeprefix(TOOL_PREFIX)
            result.tool_calls += 1
            pending[block.id] = (name, dict(block.input or {}))
        elif isinstance(block, ToolResultBlock):
            name, args = pending.get(block.tool_use_id, ("unknown", {}))
            content = _parse_result_content(block.content)
            ok = content.get("ok")
            error_type = content.get("error_type")
            result.steps.append(Step(tool=name, args=args, ok=ok, error_type=error_type))
            if name == "run_query":
                if not first_run_query_seen:
                    first_run_query_seen = True
                    result.first_try_valid = ok is True
                if error_type == "blocked":
                    result.blocked_count += 1
                if ok is True:
                    result.final_sql = args.get("sql")
                    result.final_columns = content.get("columns")
                    result.final_rows = content.get("rows")

    if usage:
        result.tokens_in = usage.get("input_tokens") or 0
        result.tokens_out = usage.get("output_tokens") or 0
    if result.final_sql is None:
        result.reason = "no_successful_query"
    else:
        result.recovered = not result.first_try_valid
    return result


# --- question-level record / replay cache ---

CACHE_DIR = Path("llm_cache") / "claude"


def _cache_key(db: str, question: str, model: str, system_prompt: str) -> str:
    payload = f"{model}\x00{db}\x00{question}\x00{system_prompt}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _read_cache(key: str) -> AgentResult | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data["steps"] = [Step(**s) for s in data.get("steps", [])]
    return AgentResult(**data)


def _write_cache(key: str, result: AgentResult) -> None:
    from dataclasses import asdict

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(asdict(result), indent=2))


async def _run_agent_sdk(
    db: str, question: str, config_path: str, model: str, system_prompt: str
) -> AgentResult:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        mcp_servers={
            MCP_SERVER_NAME: {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "safedb.server", "--config", config_path],
                "env": dict(os.environ),
            }
        },
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=MAX_TURNS,
        max_budget_usd=MAX_BUDGET_USD,
    )

    blocks: list[Any] = []
    answer: str | None = None
    usage: dict[str, Any] | None = None
    model_id = model
    started = time.monotonic()
    async for message in query(prompt=f"Database: {db}\n\nQuestion: {question}", options=options):
        if isinstance(message, AssistantMessage):
            blocks.extend(message.content)
            if message.model:
                model_id = message.model
        elif isinstance(message, ResultMessage):
            answer = message.result
            usage = message.usage if isinstance(message.usage, dict) else None
        else:
            content = getattr(message, "content", None)
            if isinstance(content, list):
                blocks.extend(content)
    latency_ms = int((time.monotonic() - started) * 1000)
    return build_result_from_blocks(blocks, answer, usage, model_id, latency_ms)


async def _gemini_fallback(db: str, question: str, config_path: str, mode: str) -> AgentResult:
    """Degrade to the Gemini per-turn path when the Claude SDK errors (production safety net)."""
    from safedb.agent import answer_question
    from safedb.config import Settings
    from safedb.llm_client import LLMClient

    settings = Settings()
    settings.llm_backend = "gemini"
    settings.llm_mode = mode
    llm = LLMClient(settings)
    return await answer_question(llm, db, question, config_path=config_path)


async def answer_question_claude(
    db: str,
    question: str,
    config_path: str,
    mode: str,
    model: str = DEFAULT_MODEL,
    fallback: bool = False,
) -> AgentResult:
    """Run one question via the Claude Agent SDK against the MCP server; honour record/replay.

    ``fallback`` (off for the eval baseline, on in production) degrades to the Gemini per-turn
    path if the Claude SDK errors, so the live site answers instead of erroring.
    """
    system_prompt = ANALYST_PROMPT.format(database=db)
    key = _cache_key(db, question, model, system_prompt)

    if mode == "replay":
        cached = _read_cache(key)
        if cached is None:
            raise CacheMiss(f"claude cache miss for {db}/{question[:30]}...; re-record")
        return cached
    cached = _read_cache(key)
    if cached is not None:
        return cached

    try:
        result = await _run_agent_sdk(db, question, config_path, model, system_prompt)
    except Exception:
        if not fallback:
            raise
        result = await _gemini_fallback(db, question, config_path, mode)

    _write_cache(key, result)
    return result
