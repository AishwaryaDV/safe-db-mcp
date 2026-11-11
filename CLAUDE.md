# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

safe-db-mcp: a read-only SQLite MCP server with a safety layer + audit log, a text-to-SQL eval
harness, a FastAPI backend, and a Next.js dashboard. Users bring their own LLM API key.

## Commands

- `make setup` — venv, install, download Chinook
- `make run` — start the MCP server over stdio
- `make api` — start the FastAPI backend on :8000
- `make test` — pytest (everything except `live_llm`)
- `make lint` — ruff check + format check
- `make eval` — replay the committed baseline eval + regression gate (no model, no key)
- `cd web && npm run dev` — dashboard on :3000; `npm run build` — type-check + build

## Layout

- `src/safedb/` — MCP server (`server.py`), safety validator (`safety.py`), audit log
  (`audit.py`), per-turn agent loop (`agent.py`), neutral LLM client (`llm_client.py`),
  FastAPI backend (`api.py`)
- `eval/` — slice builder, scorer, orchestrator, Claude Agent SDK runner
- `web/` — Next.js dashboard
- `deploy/` — systemd units, nginx, bring-up guide
- `docs/` — `PROJECT_A.md` (spec), `HARDENING.md`, `PROBLEMS_LOG.md`, `DEMO_SCRIPT.md`

## LLM backends (bring your own key)

The MCP server needs no model; only the agent/eval/dashboard call one. Set `LLM_BACKEND` in
`.env`: `anthropic_api` (your Anthropic key, recommended for hosting), `gemini` (your Gemini key),
or `claude_sdk` (a local `claude login`, dev only). `anthropic_api` falls back to Gemini on error.

## Git conventions

- Default branch: **`main`** (merge via PR). Git author: `AishwaryaDV <millamatew@gmail.com>`.
- Conventional commit style for commits and PR titles.
- No Claude/AI attribution anywhere — no `Co-Authored-By`, no "Generated with Claude Code".
- Small, atomic, single-purpose commits.
- Never commit `.env` or any API key (both are gitignored; keep them that way).

## Testing

pytest markers: `unit`, `integration`, `safety`, `live_llm`. CI and `make test` skip `live_llm`.
The eval regression gate replays a committed cache, so it needs no model or key.
