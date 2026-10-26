# safe-db-mcp — install & usage

> For anyone who installs this server. It lets an AI client (Claude Desktop, Cursor, or any
> MCP client) query **SQLite** databases **safely**: every query is validated, forced
> read-only, row-capped, time-limited, and logged. The AI can read your data but cannot
> change or damage it.
>
> Status: this guide describes the intended install and usage; it is the seed for the final
> README. Commands are finalized as the server is built.

---

## What you get

- Four read-only tools exposed over MCP: `list_databases`, `describe_schema`, `run_query`,
  `explain_query`.
- A hard safety guarantee: no writes are possible — not INSERT, UPDATE, DELETE, DROP, ALTER,
  ATTACH, PRAGMA, or multi-statement tricks. Queries are capped in rows and time.
- An audit log of **every** call, including the ones that were blocked.

## Install

```bash
git clone https://github.com/AishwaryaDV/safe-db-mcp.git
cd safe-db-mcp
make setup            # creates the environment and installs dependencies
```

## Point it at your own database

The server reads `config.yaml` — a list of the SQLite databases it may expose. Add an entry
for any `.sqlite` file on disk:

```yaml
databases:
  - name: chinook
    path: data/chinook/Chinook_Sqlite.sqlite
    description: Music store sample
  - name: my_app                       # <- your database
    path: /absolute/path/to/your_app.sqlite
    description: My application's database
limits:
  max_rows_default: 100
  max_rows_cap: 1000
  timeout_s: 3
```

Restart the server. The AI now sees `my_app` via `list_databases` and can query it safely.
Nothing else to configure.

## Use it from Claude Desktop or Cursor

Add the server to the client's MCP config (exact snippet shipped in the README at P4), for
example:

```json
{
  "mcpServers": {
    "safe-db-mcp": {
      "command": "safedb-mcp",
      "args": ["--config", "/absolute/path/to/config.yaml"]
    }
  }
}
```

Then just ask in plain English — *"How many customers are in the US?"*, *"Which artists have
the most albums?"* The AI calls `describe_schema`, writes SQL, runs it through the server, and
explains the answer. If it writes something unsafe, the server blocks it and the AI sees a
clear error instead.

## Use it over HTTP

```
POST /api/ask   {"database": "my_app", "question": "How many users signed up last week?"}
```

Streams the tool calls and the final answer as server-sent events. Also: `GET /api/audit` for
the query log and `GET /api/health` for liveness.

## Safety, limits, and what it won't do

- **Read-only, always.** There is no write path, even behind a flag.
- Every query is parsed and allow-listed to a single `SELECT`; a SQLite authorizer is a second
  wall behind the parser; the connection is opened `mode=ro` with `query_only` on.
- Results are capped (`max_rows_cap`) and queries time out (`timeout_s`).
- Every call — allowed or blocked — is written to an audit log you can inspect.
- The server never calls an LLM itself and never sees your secrets; your AI client does the
  reasoning.

## Scope & roadmap

- **v1 is SQLite only.** The server guards and queries SQLite files and nothing else.
- **Next scope:** Postgres and MySQL support. They are explicitly **out of scope for v1** and
  are the planned next expansion.
- Also out of v1: any write capability, user accounts, and the server making its own LLM calls.
