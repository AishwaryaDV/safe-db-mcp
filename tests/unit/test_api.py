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
    assert tc.get("/api/health").json() == {"status": "ok"}


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
