# Decisions

Choices the build brief left open, the default we picked, and why. Owner may override any of
these.

| Date | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| 2026-10-26 | Spider download method | Hugging Face mirror `xlangai/spider` | Most reliable programmatic pull vs the official Google Drive link; owner approved |
| 2026-10-28 | Spider databases source | Per-file from `premai-io/spider` (`database/<db_id>/<db_id>.sqlite`) | `xlangai/spider` ships questions only; this repo hosts the 169 SQLite DBs individually, so build_slice pulls just the ones its questions use (no 1 GB Drive zip) |
| 2026-10-26 | `sqlite_master` readable through `run_query` | Allowed, documented | Matches the brief's default; schema introspection is read-only and useful (hostile-query test #20) |
| 2026-10-26 | MCP SDK | `mcp` 2.3.0 — `from mcp.server.mcpserver import MCPServer` | Verified the installed API directly; in 2.x `FastMCP` was renamed to `MCPServer` |
| 2026-10-26 | Python env tooling | `venv` + `pip` (no `uv`) | `uv` is not installed on the dev machine; stick to stdlib `venv` so `make setup` works everywhere |
| 2026-10-26 | Default branch | `main` | New repo; GitHub default |
| 2026-10-26 | Multi-DB support (Postgres/MySQL) | Out of scope for v1; recorded as the next scope | Brief lists them as stretch-only; v1 is SQLite-only |
| 2026-10-26 | Deployment | Self-hosted on the owner's server (Ubuntu + nginx), both frontend and backend | Owner self-hosts all fullstack projects; not free hosts (Vercel / Render / Hugging Face Spaces) |
| 2026-10-28 | Eval model (Claude backend) | `claude-sonnet-5`, thinking disabled | Owner approved Sonnet over Opus; strong at text-to-SQL, cheaper/lighter on rate limits; model is recorded in each `run.json` |
| 2026-10-28 | Eval on both backends | Record on Claude (Sonnet 5) and also on Gemini free tier | Gemini is the deployed fallback, so the eval confirms it performs comparably through the same server (needs `GEMINI_API_KEY` when we reach it) |

## Open questions for the owner

_(none yet)_
