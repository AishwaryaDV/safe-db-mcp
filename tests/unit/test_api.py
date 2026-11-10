"""FastAPI backend: read endpoints + rate caps (agent mocked, no model/network)."""

import json

import pytest
import yaml
from fastapi.testclient import TestClient

import safedb.api as api
from safedb import audit
from safedb.agent import AgentResult, Step


@pytest.fixture
def client(tmp_path, monkeypatch):
    audit_db = tmp_path / "audit.sqlite"
    audit.init_db(audit_db)
    audit.write_audit(audit_db, source="mcp", tool="run_query", status="ok", database="chinook")
    audit.write_audit(
        audit_db,
        source="mcp",
        tool="run_query",
        status="blocked",
        database="chinook",
        error_type="blocked",
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"databases": [{"name": "chinook", "path": "x"}], "audit_db": str(audit_db)})
    )

    results = tmp_path / "results"
    (results / "run1").mkdir(parents=True)
    (results / "run1" / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "split": "tune",
                "model": "sonnet",
                "date": "2026-10-29",
                "metrics": {"execution_accuracy": 0.42},
            }
        )
    )
    (results / "run1" / "questions.jsonl").write_text(
        json.dumps({"id": "q001", "match": True, "final_sql": "SELECT 1"})
        + "\n"
        + json.dumps({"id": "q002", "match": False, "final_sql": "SELECT 2"})
        + "\n"
    )
    slice_path = tmp_path / "slice.jsonl"
    slice_path.write_text(
        json.dumps({"id": "q001", "gold_sql": "SELECT 1", "gold_result": [[1]]}) + "\n"
    )

    app = api.create_app(str(config_path), results_dir=results, slice_path=slice_path)
    return TestClient(app), monkeypatch


def test_health(client):
    tc, _ = client
    h = tc.get("/api/health").json()
    assert h["status"] == "ok" and "llm_ready" in h


def test_health_reports_missing_key(tmp_path, monkeypatch, caplog):
    import logging

    monkeypatch.setenv("LLM_BACKEND", "anthropic_api")
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    audit_db = tmp_path / "audit.sqlite"
    audit.init_db(audit_db)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"databases": [{"name": "chinook", "path": "x"}], "audit_db": str(audit_db)})
    )
    with caplog.at_level(logging.WARNING):
        app = api.create_app(str(cfg), results_dir=tmp_path / "r", slice_path=tmp_path / "s.jsonl")
    tc = TestClient(app)
    h = tc.get("/api/health").json()
    assert h["status"] == "ok" and h["llm_ready"] is False
    assert any("no API key" in r.message for r in caplog.records)


def test_audit(client):
    tc, _ = client
    rows = tc.get("/api/audit").json()["rows"]
    assert len(rows) == 2
    assert rows[0]["id"] > rows[1]["id"]  # newest first
    blocked = tc.get("/api/audit?status=blocked").json()["rows"]
    assert len(blocked) == 1 and blocked[0]["error_type"] == "blocked"


def test_eval_runs_and_questions(client):
    tc, _ = client
    runs = tc.get("/api/eval/runs").json()["runs"]
    assert runs[0]["run_id"] == "run1"
    qs = tc.get("/api/eval/runs/run1/questions?result=mismatch").json()["questions"]
    assert len(qs) == 1 and qs[0]["id"] == "q002"
    # gold is attached for the drilldown
    match = tc.get("/api/eval/runs/run1/questions?result=match").json()["questions"]
    assert match[0]["gold_sql"] == "SELECT 1"


def test_ask_streams_and_caps(client):
    tc, monkeypatch = client

    async def fake_agent(database, question, config_path, settings):
        return AgentResult(
            answer="42 tracks.",
            final_sql="SELECT count(*) FROM Track",
            final_rows=[[42]],
            steps=[
                Step(
                    tool="run_query",
                    args={"sql": "SELECT count(*) FROM Track"},
                    ok=True,
                    error_type=None,
                )
            ],
        )

    monkeypatch.setattr(api, "_run_agent", fake_agent)

    r = tc.post("/api/ask", json={"database": "chinook", "question": "how many tracks?"})
    assert r.status_code == 200
    assert "event: final" in r.text and "SELECT count(*) FROM Track" in r.text

    # per-visitor cap: 10/day total; we've used 1, so 9 more ok then 429
    for _ in range(9):
        assert tc.post("/api/ask", json={"question": "q"}).status_code == 200
    capped = tc.post("/api/ask", json={"question": "q"})
    assert capped.status_code == 429
    assert "examples" in capped.json()


def _req(host, xff=None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return type(
        "R", (), {"client": type("C", (), {"host": host})(), "headers": headers}
    )()


def test_client_ip_trusts_forwarded_only_from_trusted_peer():
    from safedb.api import _client_ip, _ip_hash

    trusted = {"127.0.0.1", "::1"}
    # trusted peer: real client comes from the LAST XFF entry (what nginx appends)
    assert _client_ip(_req("127.0.0.1", "1.1.1.1"), trusted) == "1.1.1.1"
    assert _client_ip(_req("127.0.0.1", "9.9.9.9, 2.2.2.2"), trusted) == "2.2.2.2"
    # distinct clients -> distinct buckets (the cap now actually separates visitors)
    assert _ip_hash(_req("127.0.0.1", "1.1.1.1"), trusted) != _ip_hash(
        _req("127.0.0.1", "2.2.2.2"), trusted
    )
    # untrusted peer: a client-supplied XFF is ignored, falls back to the peer
    assert _client_ip(_req("8.8.8.8", "1.1.1.1"), trusted) == "8.8.8.8"


def test_ask_rejects_oversized_question(client):
    tc, _ = client
    # over the 2000-char cap -> 400 before the agent is ever called (no model needed)
    r = tc.post("/api/ask", json={"question": "x" * 2001})
    assert r.status_code == 400 and "too long" in r.json()["error"]


def test_ask_rejects_invalid_json(client):
    tc, _ = client
    r = tc.post("/api/ask", content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_global_cap_enforced_atomically(client, monkeypatch):
    tc, _ = client

    async def fake_agent(database, question, config_path, settings):
        return AgentResult(answer="ok", final_sql="SELECT 1", final_rows=[[1]], steps=[])

    monkeypatch.setattr(api, "_run_agent", fake_agent)
    monkeypatch.setattr(api, "GLOBAL_DAILY", 2)  # tiny global budget

    assert tc.post("/api/ask", json={"question": "q1"}).status_code == 200
    assert tc.post("/api/ask", json={"question": "q2"}).status_code == 200
    capped = tc.post("/api/ask", json={"question": "q3"})  # 3rd exceeds the global cap
    assert capped.status_code == 429


def test_cors_denied_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "")  # empty -> no CORS middleware at all
    audit_db = tmp_path / "audit.sqlite"
    audit.init_db(audit_db)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"databases": [{"name": "chinook", "path": "x"}], "audit_db": str(audit_db)})
    )
    tc = TestClient(api.create_app(str(cfg), results_dir=tmp_path / "r", slice_path=tmp_path / "s"))
    r = tc.get("/api/health", headers={"origin": "http://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_allows_configured_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    audit_db = tmp_path / "audit.sqlite"
    audit.init_db(audit_db)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"databases": [{"name": "chinook", "path": "x"}], "audit_db": str(audit_db)})
    )
    tc = TestClient(api.create_app(str(cfg), results_dir=tmp_path / "r", slice_path=tmp_path / "s"))
    r = tc.get("/api/health", headers={"origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_audit_db_uses_wal(tmp_path):
    import sqlite3

    db = tmp_path / "audit.sqlite"
    audit.init_db(db)
    conn = sqlite3.connect(db)
    try:
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
    finally:
        conn.close()
    assert mode.lower() == "wal"
