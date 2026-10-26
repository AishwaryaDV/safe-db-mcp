# Decisions

Choices the build brief left open, the default we picked, and why. Owner may override any of
these.

| Date | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| 2026-10-26 | Spider download method | Hugging Face mirror `xlangai/spider` | Most reliable programmatic pull vs the official Google Drive link; owner approved |
| 2026-10-26 | `sqlite_master` readable through `run_query` | Allowed, documented | Matches the brief's default; schema introspection is read-only and useful (hostile-query test #20) |
| 2026-10-26 | MCP SDK | `mcp` 2.3.0 — `from mcp.server.mcpserver import MCPServer` | Verified the installed API directly; in 2.x `FastMCP` was renamed to `MCPServer` |
| 2026-10-26 | Python env tooling | `venv` + `pip` (no `uv`) | `uv` is not installed on the dev machine; stick to stdlib `venv` so `make setup` works everywhere |
| 2026-10-26 | Default branch | `main` | New repo; GitHub default |
| 2026-10-26 | Multi-DB support (Postgres/MySQL) | Out of scope for v1; recorded as the next scope | Brief lists them as stretch-only; v1 is SQLite-only |

## Open questions for the owner

_(none yet)_
