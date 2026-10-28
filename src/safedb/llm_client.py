"""The shared LLM client: two free backends, a response cache, and a quota guard.

Written carefully here (Project A) and copied verbatim into Project B. The rest of the code
only ever sees the neutral ``tools`` list and the neutral message shape; translation to each
backend's function-calling format happens inside the backend.

Backends:
- ``claude_sdk`` — the official ``anthropic`` SDK with a zero-arg client, which resolves the
  owner's local Claude Code / ``ant auth login`` credential automatically (no API key env var
  needed). Default model ``claude-sonnet-5``. Sonnet 5 / Opus 4.8 reject non-default
  ``temperature``, so the Claude backend omits it and disables thinking.
- ``gemini`` — free tier via the ``google-genai`` SDK, key in ``GEMINI_API_KEY``. Also the
  deployed backend and the claude_sdk fallback.

Modes (``LLM_MODE``): ``live`` (call + cache), ``record`` (call + cache), ``replay`` (cache
only; a miss raises and says to re-record). CI always runs ``replay``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from safedb.config import Settings

# --- Neutral result types (the LLMResult contract) ---------------------------


class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: dict[str, Any]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResult(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCall] = []
    usage: Usage = Usage()
    latency_ms: int = 0
    backend: str = ""
    model: str = ""
    cached: bool = False


class QuotaExceeded(RuntimeError):
    """Raised when a live/record call would exceed the daily budget."""


class CacheMiss(RuntimeError):
    """Raised in replay mode when the response is not in the committed cache."""


# --- Backend protocol --------------------------------------------------------


class Backend(Protocol):
    name: str
    default_model: str

    def generate(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        response_schema: dict[str, Any] | None,
        temperature: float,
    ) -> tuple[str | None, list[ToolCall], Usage]: ...


class ClaudeBackend:
    """Backend over the owner's local Claude Code login via the anthropic SDK."""

    name = "claude_sdk"
    default_model = "claude-sonnet-5"
    max_tokens = 4096

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy: only needed for live/record

        self._client = Anthropic()  # zero-arg: resolves the local login / profile

    def generate(self, model, messages, tools, response_schema, temperature):
        # A role=="system" message is hoisted to Anthropic's top-level system parameter.
        system = None
        convo = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                convo.append(msg)

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": self.max_tokens,
            "messages": convo,
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            # Neutral tools are already {name, description, input_schema} — Anthropic's shape.
            kwargs["tools"] = tools
        # Sonnet 5 / Opus 4.8 reject non-default temperature (400), so it is omitted. Thinking
        # is disabled to keep the multi-turn tool loop simple and the record run deterministic.
        kwargs["thinking"] = {"type": "disabled"}

        response = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                )
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return ("\n".join(text_parts) if text_parts else None, tool_calls, usage)


def gemini_tools(tools: list[dict[str, Any]] | None) -> Any:
    """Translate neutral tools into Gemini function declarations."""
    from google.genai import types

    if not tools:
        return None
    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters_json_schema=t.get("input_schema") or {"type": "object", "properties": {}},
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def gemini_contents(messages: list[dict[str, Any]]) -> tuple[str | None, list[Any]]:
    """Translate neutral messages into (system_instruction, Gemini contents)."""
    from google.genai import types

    system: str | None = None
    contents: list[Any] = []
    id_to_name: dict[str, str] = {}

    for msg in messages:
        role, content = msg["role"], msg["content"]
        if role == "system":
            system = content if isinstance(content, str) else " ".join(content)
            continue
        if isinstance(content, str):
            gem_role = "model" if role == "assistant" else "user"
            contents.append(types.Content(role=gem_role, parts=[types.Part(text=content)]))
            continue

        parts = []
        for part in content:
            kind = part["type"]
            if kind == "text":
                parts.append(types.Part(text=part["text"]))
            elif kind == "tool_use":
                id_to_name[part["id"]] = part["name"]
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(name=part["name"], args=part["input"])
                    )
                )
            elif kind == "tool_result":
                name = id_to_name.get(part["tool_use_id"], part["tool_use_id"])
                try:
                    response = json.loads(part["content"])
                except (ValueError, TypeError):
                    response = {"result": part["content"]}
                if not isinstance(response, dict):
                    response = {"result": response}
                parts.append(types.Part.from_function_response(name=name, response=response))
        contents.append(types.Content(role="model" if role == "assistant" else "user", parts=parts))
    return system, contents


class GeminiBackend:
    """Free-tier Gemini backend over the google-genai SDK."""

    name = "gemini"
    default_model = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def generate(self, model, messages, tools, response_schema, temperature):
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key) if self._api_key else genai.Client()
        system, contents = gemini_contents(messages)
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=gemini_tools(tools),
            temperature=temperature,
        )
        response = client.models.generate_content(
            model=model or self.default_model, contents=contents, config=config
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for i, part in enumerate(candidate.content.parts):
                if getattr(part, "text", None):
                    text_parts.append(part.text)
                call = getattr(part, "function_call", None)
                if call:
                    tool_calls.append(
                        ToolCall(id=f"g{i}", name=call.name, arguments=dict(call.args or {}))
                    )
        usage_meta = response.usage_metadata
        usage = Usage(
            input_tokens=getattr(usage_meta, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage_meta, "candidates_token_count", 0) or 0,
        )
        return ("\n".join(text_parts) if text_parts else None, tool_calls, usage)


_LLM_CALLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  backend TEXT NOT NULL,
  model TEXT NOT NULL,
  latency_ms INTEGER,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cached INTEGER NOT NULL,
  error TEXT,
  run_id TEXT
);
CREATE INDEX IF NOT EXISTS llm_calls_ts ON llm_calls (ts);
"""


class LLMClient:
    """Neutral entry point with caching, quota guard, fallback, and a call log."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        db_path: str | Path = "data/audit.sqlite",
        cache_dir: str | Path = "llm_cache",
        run_id: str | None = None,
        backend: Backend | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.db_path = Path(db_path)
        self.cache_dir = Path(cache_dir)
        self.run_id = run_id
        self._backend_override = backend  # used by tests
        self._init_db()

    # --- backends ---
    def _make_backend(self, name: str) -> Backend:
        if self._backend_override is not None:
            return self._backend_override
        if name == "claude_sdk":
            return ClaudeBackend()
        if name == "gemini":
            return GeminiBackend(api_key=self.settings.gemini_api_key)
        raise ValueError(f"unknown backend {name!r}")

    # --- cache ---
    def _cache_key(self, model, messages, tools, response_schema, temperature) -> str:
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "response_schema": response_schema,
                "temperature": temperature,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> LLMResult | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        return LLMResult.model_validate_json(path.read_text())

    def _write_cache(self, key: str, result: LLMResult) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(key).write_text(result.model_dump_json(indent=2))

    # --- quota + call log (llm_calls lives in the audit db) ---
    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(_LLM_CALLS_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def calls_today(self) -> int:
        """Public: number of non-cached model calls logged today (UTC)."""
        return self._calls_today()

    def _calls_today(self) -> int:
        today = datetime.now(UTC).date().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM llm_calls WHERE cached = 0 AND substr(ts, 1, 10) = ?",
                (today,),
            ).fetchone()
        finally:
            conn.close()
        return count

    def _log_call(self, result: LLMResult, error: str | None) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO llm_calls
                  (ts, backend, model, latency_ms, input_tokens, output_tokens,
                   cached, error, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    result.backend,
                    result.model,
                    result.latency_ms,
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                    int(result.cached),
                    error,
                    self.run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # --- main entry point ---
    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> LLMResult:
        backend_name = self.settings.llm_backend
        resolved_model = model or self._default_model_for(backend_name)
        key = self._cache_key(resolved_model, messages, tools, response_schema, temperature)

        # replay: cache only
        if self.settings.llm_mode == "replay":
            cached = self._read_cache(key)
            if cached is None:
                raise CacheMiss(
                    f"cache miss for {key[:12]}... in replay mode; re-record with LLM_MODE=record"
                )
            cached.cached = True
            self._log_call(cached, error=None)
            return cached

        # a warm cache short-circuits live/record too
        cached = self._read_cache(key)
        if cached is not None:
            cached.cached = True
            self._log_call(cached, error=None)
            return cached

        # live/record: a real model call, subject to the daily budget
        if self._calls_today() >= self.settings.daily_llm_budget:
            raise QuotaExceeded(
                f"daily LLM budget of {self.settings.daily_llm_budget} reached; "
                "raise DAILY_LLM_BUDGET or wait until tomorrow (UTC)"
            )

        result = self._call_with_fallback(
            backend_name, resolved_model, messages, tools, response_schema, temperature
        )
        self._write_cache(key, result)
        self._log_call(result, error=None)
        return result

    def _default_model_for(self, backend_name: str) -> str:
        return "gemini-2.5-flash" if backend_name == "gemini" else "claude-sonnet-5"

    def _call_with_fallback(
        self, backend_name, model, messages, tools, response_schema, temperature
    ) -> LLMResult:
        started = time.monotonic()
        try:
            backend = self._make_backend(backend_name)
            text, tool_calls, usage = backend.generate(
                model, messages, tools, response_schema, temperature
            )
        except Exception as exc:
            # Fallback: claude_sdk -> gemini, once.
            if backend_name == "claude_sdk" and self._backend_override is None:
                fb = self._make_backend("gemini")
                fb_started = time.monotonic()
                text, tool_calls, usage = fb.generate(
                    model, messages, tools, response_schema, temperature
                )
                return LLMResult(
                    text=text,
                    tool_calls=tool_calls,
                    usage=usage,
                    latency_ms=int((time.monotonic() - fb_started) * 1000),
                    backend="gemini",
                    model=fb.default_model,
                    cached=False,
                )
            raise exc
        return LLMResult(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=int((time.monotonic() - started) * 1000),
            backend=backend_name,
            model=model,
            cached=False,
        )
