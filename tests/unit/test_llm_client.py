"""Cache / mode / quota / call-log logic, exercised with a fake backend (no network)."""

import sqlite3

import pytest

from safedb.config import Settings
from safedb.llm_client import CacheMiss, LLMClient, QuotaExceeded, ToolCall, Usage


class FakeBackend:
    name = "claude_sdk"
    default_model = "claude-opus-4-8"

    def __init__(self):
        self.calls = 0

    def generate(self, model, messages, tools, response_schema, temperature):
        self.calls += 1
        tool_calls = [ToolCall(name="run_query", arguments={"sql": "SELECT 1"})]
        return ("answer", tool_calls, Usage(input_tokens=10, output_tokens=5))


def make_client(tmp_path, backend, **settings_over):
    settings = Settings(llm_backend="claude_sdk", llm_mode="record", daily_llm_budget=200)
    for key, value in settings_over.items():
        setattr(settings, key, value)
    return LLMClient(
        settings,
        db_path=tmp_path / "audit.sqlite",
        cache_dir=tmp_path / "llm_cache",
        backend=backend,
    )


MESSAGES = [{"role": "user", "content": "How many tracks?"}]


@pytest.mark.unit
def test_record_then_cache_hit(tmp_path):
    backend = FakeBackend()
    client = make_client(tmp_path, backend, llm_mode="record")

    first = client.generate(MESSAGES)
    assert first.cached is False
    assert first.text == "answer"
    assert first.tool_calls[0].name == "run_query"
    assert backend.calls == 1

    # identical request is served from cache; the backend is not called again
    second = client.generate(MESSAGES)
    assert second.cached is True
    assert backend.calls == 1


@pytest.mark.unit
def test_replay_miss_raises(tmp_path):
    client = make_client(tmp_path, FakeBackend(), llm_mode="replay")
    with pytest.raises(CacheMiss, match="re-record"):
        client.generate(MESSAGES)


@pytest.mark.unit
def test_replay_hit_after_record(tmp_path):
    backend = FakeBackend()
    recorder = make_client(tmp_path, backend, llm_mode="record")
    recorder.generate(MESSAGES)

    replayer = make_client(tmp_path, backend, llm_mode="replay")
    result = replayer.generate(MESSAGES)
    assert result.cached is True
    assert backend.calls == 1  # replay did not call the backend


@pytest.mark.unit
def test_quota_guard(tmp_path):
    backend = FakeBackend()
    client = make_client(tmp_path, backend, llm_mode="record", daily_llm_budget=1)
    client.generate([{"role": "user", "content": "q1"}])  # 1st real call
    with pytest.raises(QuotaExceeded, match="budget"):
        client.generate([{"role": "user", "content": "q2"}])  # 2nd would exceed


@pytest.mark.unit
def test_every_call_logged(tmp_path):
    backend = FakeBackend()
    client = make_client(tmp_path, backend, llm_mode="record")
    client.generate(MESSAGES)  # real call -> cached=0
    client.generate(MESSAGES)  # cache hit -> cached=1

    conn = sqlite3.connect(tmp_path / "audit.sqlite")
    rows = conn.execute("SELECT backend, cached FROM llm_calls ORDER BY id").fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0] == ("claude_sdk", 0)
    assert rows[1] == ("claude_sdk", 1)


@pytest.mark.unit
def test_anthropic_api_backend_selection(tmp_path):
    from safedb.llm_client import ClaudeBackend

    settings = Settings(
        llm_backend="anthropic_api", anthropic_api_key="sk-test", llm_mode="record"
    )
    client = LLMClient(
        settings, db_path=tmp_path / "audit.sqlite", cache_dir=tmp_path / "llm_cache"
    )
    assert isinstance(client._make_backend("anthropic_api"), ClaudeBackend)
    assert client._default_model_for("anthropic_api") == "claude-sonnet-5"
    assert "anthropic_api" in client._FALLS_BACK_TO_GEMINI


@pytest.mark.unit
def test_anthropic_api_falls_back_to_gemini(tmp_path, monkeypatch):
    settings = Settings(
        llm_backend="anthropic_api", anthropic_api_key="sk-test", llm_mode="record"
    )
    client = LLMClient(
        settings, db_path=tmp_path / "audit.sqlite", cache_dir=tmp_path / "llm_cache"
    )

    class Raising:
        def generate(self, *args):
            raise RuntimeError("anthropic down / bad key")

    class FakeGemini:
        default_model = "gemini-3.5-flash"

        def generate(self, *args):
            return ("fallback answer", [], Usage(input_tokens=1, output_tokens=1))

    monkeypatch.setattr(
        client, "_make_backend", lambda name: FakeGemini() if name == "gemini" else Raising()
    )

    result = client.generate(MESSAGES)
    assert result.backend == "gemini"
    assert result.text == "fallback answer"
