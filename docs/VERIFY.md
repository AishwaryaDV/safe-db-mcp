# Verification checklist (for us)

> How we see and verify each phase is actually done. Internal working doc — one phase = one
> PR, sequential, no next phase until the current gate is fully green. Full spec lives in
> [`PROJECT_A.md`](./PROJECT_A.md).

---

## P1 — Skeleton & read-only tools
**See it:** run the server, open MCP Inspector (`npx @modelcontextprotocol/inspector safedb-mcp --config config.yaml`). It lists the four tools, the `schema://{database}` resource and the `analyst` prompt. Call `list_databases` → `chinook` + table count. Call `describe_schema` on `chinook` → tables, columns, keys, 3 sample rows; with `sample_rows=0` the samples vanish.
**Verify (gate):**
- [ ] `make setup` works on a clean machine
- [ ] Inspector lists 4 tools + resource + prompt
- [ ] `list_databases` / `describe_schema` correct for Chinook, with and without samples
- [ ] Integration test starts the server over stdio with the MCP client and calls each tool — green

## P1b — Related-work research (with owner)
**See it:** read `docs/related-work.md` — a table of concrete safety checks and who enforces each.
**Verify (gate):**
- [ ] Code + docs of DBHub, Postgres MCP Pro, mcp-sqlite-readonly opened; each check in plain words with its file
- [ ] SQLite support recorded from docs (SQLite is NOT a claimed difference)
- [ ] Gaps → new test or a one-line "doesn't apply"; count updated to "32 plus N"; README Related-work drafted

## P2 — Safety layer
**See it:** in Inspector, `DROP TABLE Album` → `{ok:false, error_type:"blocked"}` (not a crash, not a dropped table). A 4-way cross join → `timeout` in a few seconds. `make test` shows all 32 attack cases go red → green.
**Verify (gate):**
- [ ] All 32 safety tests pass; authorizer-only test passes
- [ ] Data file checksums identical before/after the suite (asserted by a test)
- [ ] Coverage of `safety.py` + `executor.py` ≥ 90%

## P3 — Audit log & hints
**See it:** run a good query, a blocked query, and a typo (`SELECT Nme FROM Artist`). Typo returns a hint naming `Name`. Open `audit.sqlite` → one row per call incl. the blocked one, with status/reason/timing. `HINTS=off` → error has `message` only.
**Verify (gate):**
- [ ] Test asserts an audit row for every call, including blocked ones
- [ ] Hint tests #28–30 pass; `HINTS=off` returns message only

## P4 — Real client proof
**See it:** add the server to Claude Desktop / Cursor and ask plain-English Chinook questions; watch it call `describe_schema`, write SQL, answer. Screenshot + GIF are the artifacts.
**Verify (gate):**
- [ ] Five Chinook questions answered through a real client
- [ ] GIF recorded and saved in the repo
- [ ] Tool descriptions revised once
**Owner:** Claude Desktop or Cursor installed; Claude login active.

## P5 — Eval harness
**See it:** `python -m eval.build_slice` writes `slice.jsonl` (gold hidden). `python -m eval.run_eval --split tune --mode record` streams through questions. `eval/results/<run_id>/run.json` shows accuracy/latency/tokens. `--mode replay` reproduces the exact numbers with no key.
**Verify (gate):**
- [ ] 50 questions with gold results; leak test passes
- [ ] `record` saves; `replay` reproduces metrics exactly
- [ ] Baseline committed; CI regression gate green (fails on >3-pt drop or cache miss)
**Owner:** one free LLM backend for the record run (decided at P5 start).

## P6 — Experiments
**See it:** `python -m eval.compare` → side-by-side table with accuracy delta for each experiment. Ambiguity transcripts show ask-vs-guess.
**Verify (gate):**
- [ ] Both experiments on tune; comparison table generated from `run.json`
- [ ] Ambiguity set run; owner scores in `ambiguity_scores.csv`; script reports counts
- [ ] Final settings chosen; one holdout run recorded (never tuned on)

## P7 — Dashboard, deploy, docs
**See it:** open the live URL. `/audit` = query log with filters, blocked rows marked. `/eval` = metric cards + per-question drilldown (model attempts next to gold). `/try` = ask a question, watch it stream; hit the cap → friendly 429 with cached examples.
**Verify (gate):**
- [ ] Three pages work against the deployed API; daily caps verified by a test (429 path)
- [ ] README meets the standard (hostile-query table, five written-up failures, Related-work section)
- [ ] Live link + demo GIF in the README
