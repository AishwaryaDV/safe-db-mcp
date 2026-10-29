"""FastAPI backend for the dashboard: audit log, eval results, and a capped ask endpoint.

Read endpoints serve the three dashboard pages. ``POST /api/ask`` runs the agent (Claude
per-question with Gemini fallback in prod, or Gemini per-turn) and streams the trace as SSE,
behind per-visitor and global daily caps. Browser input never contains raw SQL.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from safedb.config import Settings, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = REPO_ROOT / "eval" / "results"
SLICE_PATH = REPO_ROOT / "eval" / "questions" / "slice.jsonl"

PER_VISITOR_DAILY = 10
GLOBAL_DAILY = 150  # below the LLM daily budget

EXAMPLES = [
    {"database": "chinook", "question": "How many tracks are in the database?"},
    {"database": "chinook", "question": "Who are the top 5 artists by number of albums?"},
    {"database": "chinook", "question": "Which 5 countries have the most customers?"},
    {"database": "chinook", "question": "What is the total revenue by billing country (top 5)?"},
]

_API_REQUESTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_requests (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, ip_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS api_requests_ts ON api_requests (ts);
"""


def _ip_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _audit_rows(audit_db: str, status, database, limit, before_id) -> list[dict[str, Any]]:
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if database:
        clauses.append("database = ?")
        params.append(database)
    if before_id:
        clauses.append("id < ?")
        params.append(before_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = sqlite3.connect(audit_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?", [*params, limit]
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def create_app(
    config_path: str = "config.yaml",
    results_dir: Path = RESULTS_DIR,
    slice_path: Path = SLICE_PATH,
) -> FastAPI:
    config = load_config(config_path)
    settings = Settings()
    gold = {}
    if slice_path.exists():
        gold = {
            r["id"]: r
            for r in (json.loads(x) for x in slice_path.read_text().splitlines() if x.strip())
        }

    # api_requests table lives alongside the audit log
    conn = sqlite3.connect(config.audit_db)
    try:
        conn.executescript(_API_REQUESTS_SCHEMA)
        conn.commit()
    finally:
        conn.close()

    app = FastAPI(title="safe-db-mcp")
    origins = [o for o in settings.allowed_origins.split(",") if o]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/audit")
    def audit(
        status: str | None = None,
        database: str | None = None,
        limit: int = 50,
        before_id: int | None = None,
    ) -> dict[str, Any]:
        return {"rows": _audit_rows(config.audit_db, status, database, min(limit, 200), before_id)}

    @app.get("/api/eval/runs")
    def eval_runs() -> dict[str, Any]:
        runs = []
        for path in sorted(results_dir.glob("*/run.json")):
            meta = json.loads(path.read_text())
            runs.append(
                {k: meta.get(k) for k in ("run_id", "split", "experiment", "model", "date")}
                | {"metrics": meta.get("metrics")}
            )
        runs.sort(key=lambda m: m.get("date") or "", reverse=True)
        return {"runs": runs}

    @app.get("/api/eval/runs/{run_id}")
    def eval_run(run_id: str) -> Any:
        path = results_dir / run_id / "run.json"
        if not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return json.loads(path.read_text())

    @app.get("/api/eval/runs/{run_id}/questions")
    def eval_questions(run_id: str, result: str | None = None) -> dict[str, Any]:
        path = results_dir / run_id / "questions.jsonl"
        if not path.exists():
            return {"questions": []}
        records = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        if result == "match":
            records = [r for r in records if r["match"]]
        elif result == "mismatch":
            records = [r for r in records if not r["match"]]
        for r in records:  # attach gold (shown only here, never in a model request)
            g = gold.get(r["id"], {})
            r["gold_sql"] = g.get("gold_sql")
            r["gold_result"] = g.get("gold_result")
        return {"questions": records}

    @app.get("/api/examples")
    def examples() -> dict[str, Any]:
        return {"examples": EXAMPLES}

    def _count(where: str, params: list[Any]) -> int:
        today = datetime.now(UTC).date().isoformat()
        conn = sqlite3.connect(config.audit_db)
        try:
            (n,) = conn.execute(
                f"SELECT COUNT(*) FROM api_requests WHERE substr(ts,1,10)=? {where}",
                [today, *params],
            ).fetchone()
        finally:
            conn.close()
        return n

    def _record_request(ip_hash: str) -> None:
        conn = sqlite3.connect(config.audit_db)
        try:
            conn.execute(
                "INSERT INTO api_requests (ts, ip_hash) VALUES (?, ?)",
                [datetime.now(UTC).isoformat(), ip_hash],
            )
            conn.commit()
        finally:
            conn.close()

    @app.post("/api/ask")
    async def ask(request: Request) -> Any:
        body = await request.json()
        database = body.get("database", "chinook")
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "question is required"}, status_code=400)

        ip_hash = _ip_hash(request)
        if (
            _count("AND ip_hash=?", [ip_hash]) >= PER_VISITOR_DAILY
            or _count("", []) >= GLOBAL_DAILY
        ):
            return JSONResponse(
                {
                    "error": "daily limit reached",
                    "examples": EXAMPLES,
                    "message": "You've hit today's question limit. Try the cached examples.",
                },
                status_code=429,
            )
        _record_request(ip_hash)

        result = await _run_agent(database, question, config_path, settings)

        async def stream():
            for step in result.steps:
                yield _sse("tool_call", {"tool": step.tool, "args": step.args})
                yield _sse(
                    "tool_result", {"tool": step.tool, "ok": step.ok, "error_type": step.error_type}
                )
            yield _sse(
                "final",
                {
                    "answer": result.answer,
                    "final_sql": result.final_sql,
                    "columns": result.final_columns,
                    "rows": result.final_rows,
                },
            )

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.state.config = config
    return app


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _run_agent(database: str, question: str, config_path: str, settings: Settings):
    """Dispatch to the configured backend (Claude per-question + fallback, or Gemini per-turn)."""
    if settings.llm_backend == "claude_sdk":
        from eval.claude_runner import answer_question_claude

        return await answer_question_claude(
            database, question, config_path, settings.llm_mode, fallback=True
        )
    from safedb.agent import answer_question
    from safedb.llm_client import LLMClient

    llm = LLMClient(settings, db_path=load_config(config_path).audit_db)
    return await answer_question(llm, database, question, config_path=config_path)


app = create_app()
