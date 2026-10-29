# Problems & solutions log (per phase)

A running record of the real snags we hit each phase and how we resolved them — the "what
actually went wrong and what we did about it" that doesn't show up in the commit history.

---

## P1 — Skeleton & read-only tools

- **The MCP Python SDK API had changed, and web search was unreliable.** WebSearch/WebFetch
  gave conflicting, partly-hallucinated answers (`FastMCP` vs `MCPServer`, a wrong version,
  invented dependencies).
  **Solution:** stopped trusting web summaries — `pip install`ed the real package and
  introspected it. Found `mcp` **2.3.0**, where `FastMCP` was renamed to `MCPServer`; confirmed
  the decorator API and `mcp.run("stdio")` directly, then built `server.py` against that.

- **TLS certificate verification failed on the Chinook download.** The macOS python.org
  interpreter ships without a usable CA bundle, so `urllib` raised
  `SSLCertVerificationError`.
  **Solution:** build an SSL context from `certifi`'s CA bundle and add `certifi` as a
  dependency, so `make setup` works on a clean machine.

- **`ruff format` reflowed the Python code blocks inside our Markdown docs**, clobbering
  intended formatting in `PROJECT_A.md` / the brief.
  **Solution:** scoped ruff to Python only (`extend-exclude = ["*.md"]`) and restored the docs.

- **MCP Inspector is a GUI, so it can't be the automated proof.**
  **Solution:** proved the server over stdio with the real MCP *client* in an integration test
  (same protocol the Inspector/Claude Desktop use); left the Inspector as a manual spot-check.

## P1b — Related-work research

- **Needed to claim "differences" honestly without overclaiming, and READMEs weren't enough.**
  **Solution:** shallow-cloned and read the actual **source** of DBHub, Postgres MCP Pro, and
  mcp-sqlite-readonly; built a comparison table with file/line references; only claimed a
  difference when a code citation backed it. Result: SQLite support and a SQLite row cap are
  **not** differences; the audit log, the authorizer, a SQLite statement timeout, and
  AST-level validation **are**.

- **mcp-sqlite-readonly splits statements with a naive `split(';')`.**
  **Solution:** added hostile-query test #40 (`SELECT ';' ; DROP TABLE Album`) — a case that
  beats a naive splitter, which our parser-based "exactly one statement" rule handles.

## P2 — Safety layer

- **sqlglot parses odd inputs in non-obvious ways**, so the validator couldn't be written from
  assumptions (`SAVEPOINT` → `Alias`, `REINDEX` → `Column`, empty string → `[None]`).
  **Solution:** empirically probed sqlglot on every hostile input first, then built the
  validator on the observed AST: root must be `Select`/`Union`/set-op, walk-and-deny write
  node types, deny dangerous functions by name. The odd cases fall out of the root allow-list.

- **The timeout tests wouldn't fire with a plain `SELECT`** — the row cap short-circuits a big
  result before the stopwatch matters.
  **Solution:** used `count(*)` over a 4-way cross join and an endless recursive CTE, which
  force full evaluation, so the progress-handler timeout actually triggers.

- **`elapsed_ms` was `None` on the timeout path**, failing the "timed out promptly" assertion.
  **Solution:** populate `elapsed_ms` in the executor's error branch too.

## P3 — Audit log & hints

- **The brief put the audit write "in the executor's `finally`," but two of the four tools
  don't go through the executor** — and the gate requires *every* tool call to be logged.
  **Solution:** audit at the server (tool boundary) via an `_audit_call` context manager
  wrapping all four tools, so ok/blocked/failed calls all log exactly one row. Recorded the
  deviation in `DECISIONS.md`.

- Minor: ruff `UP017` → switched to the `datetime.UTC` alias.

## P4 — Real client proof

- **Can't operate a desktop GUI (Claude Desktop) or screen-record it from here.**
  **Solution:** proved functionality with the automated stdio integration test (identical MCP
  protocol); deferred the demo GIF/screenshot and the one tool-description tweak to the
  end-of-project capture pass (the punch-list in `VERIFY.md`).

## P5 — Eval harness

- **How to call Claude on the owner's local login without an API key** (the `claude_sdk`
  backend).
  **Solution:** the official `anthropic` SDK with a zero-arg `Anthropic()` client resolves the
  local Claude Code / `ant auth login` credential automatically (confirmed via the claude-api
  reference). No key needed for development or the record run.

- **Sonnet 5 / Opus 4.8 reject non-default `temperature` and thinking config with a 400.**
  **Solution:** the Claude backend omits `temperature` and sets `thinking: disabled`.

- **A multi-turn tool loop needs the assistant's `tool_use` ids to match the following
  `tool_result` ids**, but the neutral `LLMResult` had abstracted the id away — and leaving
  thinking on would also require echoing thinking blocks back unchanged.
  **Solution:** thread the real `tool_use` id through the neutral `ToolCall`, and disable
  thinking to avoid the thinking-block replay requirement. Replay stays deterministic because
  the recorded responses (with their ids) are replayed in the same order, producing identical
  cache keys.

- **The chosen Spider mirror (`xlangai/spider`) ships questions only — no database files**, so
  gold results couldn't be computed (you can't run SQL without the database).
  **Solution:** a two-source plan — questions + gold SQL from `xlangai/spider`, and the SQLite
  databases per-file from `premai-io/spider` (fetch only the ones the slice uses; no 1 GB Drive
  zip). Recorded in `DECISIONS.md` / `DATA_SOURCES.md`.

- **The `claude_sdk` backend first used the raw `anthropic` API SDK, which demanded an API
  key** — but the owner (like Offroute / reddit-outreach) uses the **Claude Code subscription,
  no API keys**.
  **Solution:** switched the Claude path to the **Claude Agent SDK** (`claude-agent-sdk`), which
  runs on the local Claude Code login. Because that SDK runs its own loop (it won't hand a tool
  call back for us to execute), the Claude path is **per-question** — the Agent SDK drives the
  MCP server directly — while Gemini stays on our per-turn loop. Both score identically.

- **Gemini free tier = 20 `generate_content` requests/day/model** — far below the ~100–150 an
  agentic 50-question eval needs, so the full baseline can't be recorded on the free tier in a
  day. **Solution:** documented the limit; the baseline is recorded on the Claude subscription
  (Sonnet) instead, with Gemini kept as the deployed backend + a smaller comparison.

- **Gemini model/compat churn:** `gemini-2.5-flash` is retired for new keys (404); Gemini 3.x
  requires echoing a `thought_signature` back on `functionCall` parts (400 without it); and the
  endpoint throws transient 503/429.
  **Solution:** pin `gemini-3.5-flash`, thread the `thought_signature` through the neutral
  `ToolCall`, and add exponential-backoff retry for 429/503.

- **The leak detector false-positived when the model wrote the same SQL as the gold** (the
  model being *correct* looked like a leak).
  **Solution:** scope the leak check to content we *author* (system prompt + question), not the
  model's own tool calls or the results derived from them.
