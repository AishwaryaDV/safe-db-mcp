# Project A: Phased Implementation Plan

> How we build `safe-db-mcp`, phase by phase. Derived from the milestones in
> [`PROJECT_A.md`](./PROJECT_A.md). Each phase is **one pull request**, sequential and gated:
> we do not start the next phase until every check in the current one passes. Many small,
> atomic commits inside each PR.
>
> Every phase below says **how to see it** (visualize the result yourself) and **how to
> verify it** (the gate that must pass). Commands are the intended interface; exact flags are
> settled when we build each phase.

---

## What the finished product does (why the phases add up)

A local server that lets an AI client query SQLite databases **safely** — every query
validated, read-only, row-capped, time-limited, and logged — plus a harness that **measures**
how accurately a model answers benchmark questions through it.

**Using it over your own database:** add an entry to `config.yaml` pointing at any `.sqlite`
file, restart, done. v1 is SQLite-only by design.

**Three ways it's consumed:** (1) inside Claude Desktop / Cursor as an MCP server, (2) over
HTTP via `POST /api/ask`, (3) the `/try` web page. The payoff is a provably read-only bridge
with a full audit log, plus an honest measured accuracy number.

---

## Cadence and ground rules

- One PR per phase; checks must pass before the next phase starts.
- `DECISIONS.md` records every open choice and the default we picked.
- No LLM key needed until **P5**. CI never calls a model (it runs `replay` from cached
  answers). GitHub Actions is free for public repos.
- Every metric in the README/dashboard is produced by a script in the repo — never typed by
  hand.

---

## P1 — Skeleton & read-only tools  (milestone M1)

**Goal:** a runnable MCP server scaffold with the two read tools working against Chinook.

**What we build:** repo scaffold (`pyproject.toml`, `ruff`, `pytest`, `Makefile`,
`config.yaml` + loader, `.env.example`, MIT licence, `.gitignore`, `DECISIONS.md`,
`scripts/download_data.py`), the MCP server over stdio registering all four tools + the
resource + the `analyst` prompt, and full implementations of `list_databases` and
`describe_schema` (`run_query`/`explain_query` are registered but get their real safety in P2).

**How to see it:**
- Run the server and open the **MCP Inspector** (`npx @modelcontextprotocol/inspector safedb-mcp --config config.yaml`).
- You'll see the four tools, the `schema://{database}` resource, and the `analyst` prompt listed.
- Call `list_databases` → returns `chinook` with its table count.
- Call `describe_schema` on `chinook` → see its tables, columns, keys, and 3 sample rows;
  call it with `sample_rows=0` → the sample field disappears.

**How to verify it (gate):**
- [ ] `make setup` works on a clean machine
- [ ] Inspector lists the four tools, the resource, and the prompt
- [ ] `list_databases` / `describe_schema` return correct Chinook data, with and without samples
- [ ] `make test` runs an integration test that starts the server over stdio with the MCP
      client and calls each tool — green

**Blockers:** none (I download Chinook; you later confirm its source in `DATA_SOURCES.md`).

---

## P1b — Related-work research  (milestone M1b, with you)

**Goal:** learn what real DB-MCP servers check for safety *before* we write our own layer, so
their checks become extra tests.

**What we build:** `docs/related-work.md` — a comparison table (check × DBHub / Postgres MCP
Pro / mcp-sqlite-readonly / this project + matching test number). New safety tests for any gap
that applies to SQLite (red until P2).

**How to see it:** read `docs/related-work.md`; each row is a concrete safety check and who
enforces it. Every difference we'll later claim in the README traces to a row here.

**How to verify it (gate):**
- [ ] Code + docs of the three servers opened; each check written in plain words with its file
- [ ] SQLite support recorded from docs (SQLite is **not** a claimed difference)
- [ ] Gaps marked; each becomes a new test or a one-line "why it doesn't apply"
- [ ] Hostile-query count updated to "32 plus N"; README Related-work section drafted

**Blockers:** ~2–3h together. I do the legwork and bring you the table; you can supply sources.

---

## P2 — Safety layer  (milestone M2)

**Goal:** make every dangerous query impossible, proven by tests.

**What we build:** all 32 hostile-query tests first (watch them fail), then `safety.py` (the
11-step validator: size → parse → one statement → SELECT-only allow-list → deny dangerous
functions → read-only connection → authorizer → timeout → row/cell caps), and `executor.py`.

**How to see it:**
- In the Inspector, send `DROP TABLE Album` to `run_query` → you get a clean
  `{ok:false, error_type:"blocked"}`, not a crash and not a dropped table.
- Try a 4-way cross join → it `timeout`s within a few seconds instead of hanging.
- Run `make test` and watch all 32 attack cases go from red to green.

**How to verify it (gate):**
- [ ] All 32 safety tests pass; the authorizer-only test passes
- [ ] Data file checksums identical before and after the whole suite (a test asserts it)
- [ ] Coverage of `safety.py` + `executor.py` ≥ 90%

**Blockers:** none.

---

## P3 — Audit log & hints  (milestone M3)

**Goal:** every call is logged (even blocked ones); typos get helpful hints.

**What we build:** `audit.py` (writes each call to `audit.sqlite` on a separate writable
connection, in a `finally` block) and `hints.py` (difflib "did you mean…").

**How to see it:**
- Run a good query, a blocked query, and a typo (`SELECT Nme FROM Artist`) through Inspector.
- The typo returns a hint listing `Name`.
- Open `audit.sqlite` (a small script or `sqlite3`) and see one row per call — including the
  blocked one — with status, reason, timing.
- Set `HINTS=off` and confirm the error now returns only `message`, no hint.

**How to verify it (gate):**
- [ ] A test asserts an audit row exists for every call, including blocked ones
- [ ] Hint tests for typos (#28–30) pass; `HINTS=off` returns message only

**Blockers:** none.

---

## P4 — Real client proof  (milestone M4)

**Goal:** show it working inside a real AI client, not just tests.

**What we build:** config snippets for Claude Desktop and Cursor in the README; answer five
Chinook questions live; capture a screenshot and a demo GIF; revise tool descriptions once
based on anything the client got wrong.

**How to see it:**
- Add the server to Claude Desktop / Cursor, then ask in plain English: *"How many tracks are
  there?"*, *"Which artists have the most albums?"*, *"Who are the top-spending customers?"*
- Watch the AI call `describe_schema`, write SQL, call `run_query`, and answer.
- The screenshot + GIF are the visual artifact.

**How to verify it (gate):**
- [ ] Five Chinook questions answered through a real client
- [ ] GIF recorded and saved in the repo
- [ ] Tool descriptions revised once

**Blockers:** you need **Claude Desktop or Cursor installed** and your Claude login active.

---

## P5 — Eval harness  (milestone M5)

**Goal:** measure how accurately a model answers 50 Spider questions through the server, and
make the result reproducible with no keys.

**What we build:** `llm_client.py` (the shared contract — two free backends, cache, call log,
quota guard), `agent.py` (the MCP-client tool-calling loop), `eval/build_slice.py` (pick 50
questions + compute gold answers), `run_eval.py`, `score.py`. Record a baseline run, commit
its cache + `eval/baseline.json`, and wire the CI regression gate.

**How to see it:**
- `python -m eval.build_slice` → writes `slice.jsonl` (50 questions, gold answers hidden from
  the model).
- `python -m eval.run_eval --split tune --mode record` → streams through the questions.
- Open `eval/results/<run_id>/run.json` → see execution accuracy, first-try rate, recovery
  rate, latency, tokens.
- `--mode replay` → reruns from cache with **no key** and reproduces the exact same numbers.

**How to verify it (gate):**
- [ ] 50 questions with gold results; the leak test (gold never shown to the model) passes
- [ ] `record` run saves; `replay` reproduces metrics exactly
- [ ] Baseline committed; CI regression gate green (fails on >3-point drop or a cache miss)

**Blockers:** one free LLM backend for the **record** run (your Claude login or a Gemini key).
Decided at the start of this phase.

---

## P6 — Experiments  (milestone M6)

**Goal:** show what actually moves accuracy, and how the model handles ambiguous questions.

**What we build:** `eval/compare.py` and two A/B experiments on the tune split — sample rows
on vs off, hints on vs off — plus the ambiguity set, then one final holdout run.

**How to see it:**
- `python -m eval.compare` → a side-by-side table of the two experiments with the accuracy
  delta for each.
- The ambiguity transcripts show whether the model asked a clarifying question or guessed.

**How to verify it (gate):**
- [ ] Both experiments run on tune; comparison table generated from `run.json` files
- [ ] Ambiguity set run; your good/bad scores entered in `ambiguity_scores.csv`; a script
      reports counts
- [ ] Final settings chosen; one holdout run recorded (holdout is never tuned on)

**Blockers:** you score the ambiguity answers (a short CSV).

---

## P7 — Dashboard, deploy, docs  (milestone M7)

**Goal:** a deployed site that shows the audit log, the eval results, and a live "ask a
question" demo — and a README that meets the standard.

**What we build:** `api.py` (FastAPI: audit/eval/examples endpoints + the SSE `/api/ask` with
daily caps), the Next.js dashboard (`/audit`, `/eval`, `/try`), deploy to free hosts, and the
README with the demo GIF, script-generated results tables, and five real failure write-ups.

**How to see it:**
- Open the live URL.
- `/audit` → the query log with filters; blocked rows visibly marked.
- `/eval` → metric cards and a per-question drilldown (click a row → the model's attempts next
  to the gold answer).
- `/try` → ask a question, watch each step stream; hit the limit and see the friendly 429 with
  cached examples.

**How to verify it (gate):**
- [ ] Three pages work against the deployed API; daily caps verified by a test (429 path)
- [ ] README meets the standard, including the hostile-query results table, five written-up
      failures, and the Related-work section built from `docs/related-work.md`
- [ ] Live link + demo GIF in the README

**Blockers:** a deploy host sign-in (free tier); Gemini key for the live demo's LLM.

---

## Owner blockers, summarized

| Phase | What we need from you |
| --- | --- |
| P1 | Confirm Chinook/Spider sources in `DATA_SOURCES.md` (one glance) |
| P1b | ~2–3h research together |
| P4 | Claude Desktop or Cursor installed; Claude login active |
| P5 | One free LLM backend for the record run (Claude login or Gemini key) |
| P6 | Score the ambiguity answers in a CSV |
| P7 | Deploy-host sign-in; Gemini key for the live demo |
