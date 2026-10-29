# safe-db-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that lets an AI client query
**SQLite** databases **safely** — every query parsed, forced read-only, row-capped,
time-limited, and logged — plus an **eval harness** that measures how accurately a model
answers benchmark questions *through* that server, and a dashboard to explore it all.

<!-- TODO(demo): add demo.gif and the live link once deployed -->
> **Live demo:** _coming soon_ · **Demo:** `docs/demo.gif` _(added at deploy)_

---

## Why

Giving a model raw database access is risky: it can write, drop, exfiltrate whole tables, or
hang the database with a runaway query. safe-db-mcp is the narrow waist in between. The model
only ever sees four read-only tools — `list_databases`, `describe_schema`, `run_query`, and
`explain_query` — and every call goes through a safety layer before it touches SQLite:

- **Read-only.** Statements are parsed with `sqlglot`; only `SELECT`/`WITH` (and set
  operations) are allowed. Anything that writes, attaches, pragmas, or chains multiple
  statements is rejected before execution.
- **Bounded.** A `LIMIT` is injected if missing (default 100, hard cap 1000), queries run under
  a wall-clock timeout, and oversized cells are truncated.
- **Observable.** Every query — allowed *or blocked* — is written to an append-only audit log
  with the SQL, status, row count, and timing.
- **Helpful.** On a malformed query or unknown column the server returns a "did you mean" hint
  (closest table/column by edit distance) so the model can recover instead of guessing.

## The eval — does safe querying still work?

A safety layer is only worth it if a model can still get the right answer through it. The
harness measures that on a reproducible slice of the [Spider](https://yale-lily.github.io/spider)
text-to-SQL benchmark (seed 42; 30 tune / 20 holdout questions across several databases).

For each question the agent is given only the MCP tools and the plain-English question. It
explores the schema, writes SQL, runs it, recovers from errors, and returns an answer. We
compare the **result set** (not the SQL string) against the gold query's result — order-insensitive
unless the question implies ordering.

### Baseline (tune split, Claude Sonnet)

| Metric | Value |
| --- | --- |
| Execution accuracy | **42.3%** (11 / 26 scored) |
| First-try-valid rate | 92.3% |
| Recovery rate (after a bad first query) | 50% |
| Blocked-query rate | 0% |
| Mean tool calls / question | 3.2 |

4 of the 30 questions are excluded as *unscorable* (their gold query returns an empty result on
the shipped database — a known Spider `flight_2` whitespace quirk — so there is nothing to match
against). Accuracy is computed over the 26 scorable questions. Accuracy by difficulty:
easy 62.5%, medium 50%, hard 0%, extra 28.6%. The remaining misses are genuine (e.g. mis-reading
"on average", returning ties without a `LIMIT`); see [`docs/PROBLEMS_LOG.md`](docs/PROBLEMS_LOG.md).

### Reproduce it — no API key, no tokens

The baseline run is committed along with its LLM cache, so CI (and you) can replay it exactly
with no model call and no key:

```bash
make eval        # replays the committed cache, recomputes 42.3%, fails on >3pt regression
```

`live` mode calls the model and `record` writes the cache; `replay` (above) is deterministic.
See [`docs/USAGE.md`](docs/USAGE.md) for running your own experiments and the holdout split.

## Dashboard

A Next.js app (in [`web/`](web/)) over the FastAPI backend ([`src/safedb/api.py`](src/safedb/api.py)):

- **Try it** — ask a plain-English question and watch each tool call stream back live (SSE),
  ending in the answer, the SQL, and the result table. Capped at 10/visitor and 150/day.
- **Eval** — browse runs, metric cards, and every question that passed or failed with the
  model's SQL next to the gold SQL.
- **Audit log** — every query the server saw, including blocked ones, with status and timing.

## Architecture

```
 Next.js dashboard ──HTTP/SSE──▶ FastAPI (api.py) ──▶ agent loop ──MCP/stdio──▶ safedb server
        web/                         read + /ask          eval/ + agent.py        safety + audit + SQLite
```

- `src/safedb/` — the MCP server (`server.py`), safety validator (`safety.py`), audit log
  (`audit.py`), the per-turn agent loop (`agent.py`), the neutral LLM client with Claude↔Gemini
  fallback (`llm_client.py`), and the HTTP backend (`api.py`).
- `eval/` — slice builder, scorer, orchestrator, and the Claude Agent SDK runner.
- `web/` — the dashboard.

**LLM backends.** Claude is primary via the Claude Agent SDK (uses the local Claude Code login,
no API key); Gemini is the fallback/overflow path. In production the live site falls back to
Gemini if Claude is unavailable or over budget — see [`DECISIONS.md`](DECISIONS.md).

## Quick start

```bash
make setup     # create the virtualenv, install the package, download Chinook
make run       # start the MCP server over stdio
make api       # start the FastAPI backend on :8000
make test      # run the test suite
make lint      # ruff lint + format check
make eval      # replay the committed baseline eval + regression gate

cd web && npm ci && npm run dev   # dashboard on :3000
```

## Docs

- [`docs/USAGE.md`](docs/USAGE.md) — install and usage
- [`docs/PROJECT_A.md`](docs/PROJECT_A.md) — full specification
- [`docs/VERIFY.md`](docs/VERIFY.md) — per-phase verification checklist
- [`docs/PROBLEMS_LOG.md`](docs/PROBLEMS_LOG.md) — problems hit per phase and how they were solved
- [`docs/related-work.md`](docs/related-work.md) — how this compares to prior text-to-SQL work
- [`deploy/README.md`](deploy/README.md) — self-hosted Ubuntu + nginx bring-up
- [`DECISIONS.md`](DECISIONS.md) · [`DATA_SOURCES.md`](DATA_SOURCES.md)

## Licence

MIT. See [`LICENSE`](LICENSE). Bundled data (Chinook, Spider) is downloaded locally and never
committed; see [`DATA_SOURCES.md`](DATA_SOURCES.md).
