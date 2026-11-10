# Production Hardening Tracker

Findings from the security + production-readiness audit (branch `feat/byok-llm-backend`,
2026-11-10). Each item is fixed on its own commit, verified against the test suite to avoid
regressions, and checked off here. Context: this is a **bring-your-own-key public endpoint**, so
the threat model is dominated by *cost/abuse control* (someone draining the owner-or-host's key)
on top of the usual read-only-database safety.

**What is already solid (do not regress):**
- Safety layer holds against every probed bypass (multi-statement, PRAGMA, ATTACH, writable CTEs,
  table-functions, comment tricks) — two independent walls (sqlglot validator + runtime
  read-only connection with authorizer).
- Secrets hygiene: `.env` is gitignored and never committed; no keys in `llm_cache/` or the audit DB.
- 116 tests pass, ruff clean.

## Status

| ID | Sev | Title | Status |
|----|-----|-------|--------|
| C1 | CRITICAL | Per-visitor rate cap non-functional behind nginx | ☑ fixed |
| H1 | HIGH | No request-body / question size limit on `/api/ask` | ☑ fixed |
| H2 | HIGH | Rate-limit check-then-insert is racy (TOCTOU) | ☑ fixed |
| H3 | HIGH | No startup validation that a key exists for the backend | ☑ fixed |
| H4 | HIGH | CORS falls back to `*` | ☑ fixed |
| M1 | MED | SQLite write contention under async uvicorn | ☐ |
| M2 | MED | SSE isn't actually streamed (whole agent runs first) | ☐ |
| M3 | MED | `bypassPermissions` lacks a guard test | ☐ |
| M4 | MED | `api_requests` / audit tables grow unbounded | ☐ |
| M5 | MED | Raw exception text can reach the client | ☐ |
| L1 | LOW | TLS/HSTS not baked into nginx template | ☐ |
| L2 | LOW | No healthcheck wired into systemd; no `web/` CI | ☐ |
| L3 | LOW | `{run_id}` path param defense-in-depth | ☐ |

---

## CRITICAL

### C1 — Per-visitor rate cap is non-functional behind nginx
- **Where:** `src/safedb/api.py:45` (`_ip_hash`), `deploy/nginx.conf`, `deploy/safe-db-mcp-api.service`
- **Problem:** The cap keys off `request.client.host`. Behind nginx the connecting peer is always
  the loopback proxy (`127.0.0.1`), so every visitor hashes to the same bucket. The per-visitor
  cap (10/day) is meaningless and one abuser drains the whole `GLOBAL_DAILY` budget — real money
  on a keyed backend.
- **Fix (app-level, launch-independent):** read the client IP from `X-Forwarded-For` **only when
  the direct peer is a trusted proxy** (new `trusted_proxies` setting, default `127.0.0.1,::1`).
  nginx appends the real client with `$proxy_add_x_forwarded_for`, so take the **last** XFF entry
  (the one the trusted proxy added — unspoofable by the client). Untrusted peers fall back to
  `request.client.host`, so a client that injects its own XFF header is ignored.
- **Verify:** unit test — (a) trusted peer + XFF → distinct hashes per client IP (separate
  buckets); (b) untrusted peer + spoofed XFF → ignored, falls back to peer. Re-run full suite.

## HIGH

### H1 — No request-body / question size limit on `/api/ask`
- **Where:** `src/safedb/api.py:181`
- **Problem:** `await request.json()` reads an unbounded body; `question` is sent to the model with
  no length cap — cheap memory/DoS vector and inflated token spend before any cap check.
- **Fix:** reject `question` longer than a cap (2000 chars) with 400; document nginx
  `client_max_body_size 16k` for `/api/`.
- **Verify:** unit test posting an over-length question returns 400 and never calls the agent.

### H2 — Rate-limit check-then-insert is racy (TOCTOU)
- **Where:** `src/safedb/api.py:188-200`
- **Problem:** count and insert are separate statements/connections; concurrent requests all read
  "under cap" before any insert lands, overshooting the global/visitor cap under burst — directly
  over-spends the budget.
- **Fix:** make count + insert atomic — a single conditional
  `INSERT ... SELECT ... WHERE (SELECT COUNT(*) ...) < cap`, treating "0 rows inserted" as "capped".
- **Verify:** unit test that the atomic insert refuses once the cap is reached; existing cap test
  still passes.

### H3 — No startup validation that a key exists for the selected backend
- **Where:** `src/safedb/api.py:245` (module-level `app = create_app()`), `src/safedb/config.py`
- **Problem:** a misconfigured prod (`LLM_BACKEND=anthropic_api`, blank key) boots "healthy"; every
  ask fails at call time and silently falls back to Gemini (or errors if that's blank too) — after
  already consuming a rate slot.
- **Fix:** on startup, if backend is `anthropic_api`/`gemini` and its key is blank and mode isn't
  `replay`, log a loud warning (and surface it on `/api/health`). Don't hard-crash — read-only
  pages must still serve.
- **Verify:** unit test that `create_app` with a keyless metered backend logs/warns; health
  reports the degraded state.

### H4 — CORS falls back to `*`
- **Where:** `src/safedb/api.py:96-102`
- **Problem:** empty `ALLOWED_ORIGINS` → `allow_origins=["*"]` with `*` methods/headers; any origin
  can drive `/api/ask` from a victim's browser and burn the budget.
- **Fix:** default to **deny** cross-origin (empty → no CORS middleware / empty origins). Keep an
  explicit opt-in (`ALLOWED_ORIGINS=*`) for local dev, documented as unsafe for prod.
- **Verify:** unit test — no `ALLOWED_ORIGINS` → cross-origin preflight is not allowed; set origin
  is allowed.

## MEDIUM

### M1 — SQLite write contention under async uvicorn
- **Where:** `src/safedb/api.py` (per-request `sqlite3.connect`), `src/safedb/audit.py`, `llm_client.py`
- **Problem:** every request opens a fresh default connection (rollback journal, 5s busy) and the
  async ask path runs blocking SQLite + the agent on the event loop; concurrent asks serialize and
  can hit `database is locked`.
- **Fix:** enable `PRAGMA journal_mode=WAL` + a `busy_timeout` on the audit DB; run the blocking
  agent call via `run_in_threadpool`.
- **Verify:** existing tests pass; add a small concurrency smoke (two overlapping asks) if cheap.

### M2 — SSE isn't actually streamed
- **Where:** `src/safedb/api.py:202-220`
- **Problem:** `result = await _run_agent(...)` fully completes before `stream()` yields; a slow
  multi-turn answer can exceed the nginx `proxy_read_timeout` with nothing shown. Correctness/UX,
  not security.
- **Fix:** emit steps as the agent produces them (push a callback/queue from the agent loop), or at
  minimum send an early `event: start` so the connection stays warm; align the nginx timeout.
- **Verify:** test that a `start`/early event is flushed before the final event.

### M3 — `bypassPermissions` lacks a guard test
- **Where:** `eval/claude_runner.py:141`
- **Problem:** acceptable today (tools are allow-listed to the 4 read-only MCP tools) but nothing
  pins it — a future edit could widen the allow-list.
- **Fix:** add a test asserting `allowed_tools` contains only `mcp__safedb__*` and no built-in
  file/bash tool is permitted.
- **Verify:** the new test.

### M4 — `api_requests` / audit tables grow unbounded
- **Where:** `src/safedb/api.py:37-42`
- **Problem:** one row per ask forever; slow leak + slower counts over time.
- **Fix:** prune `api_requests` older than N days on write (cheap) or a daily rollup; document audit
  retention.
- **Verify:** test that rows older than the window are pruned.

### M5 — Raw exception text can reach the client
- **Where:** `src/safedb/api.py` (`/api/ask`), surfaced in `web/app/try/page.tsx`
- **Problem:** an unhandled exception in `/api/ask` (e.g. backend/key failure) returns FastAPI's
  default 500 and the message bubbles to the UI.
- **Fix:** wrap `/api/ask` in try/except returning a generic error payload; log the detail server-side.
- **Verify:** test that a forced agent exception yields a generic 500 body (no internal text).

## LOW

### L1 — TLS/HSTS not in the nginx template
- **Where:** `deploy/nginx.conf`
- **Fix:** ship a hardened template (HTTP→HTTPS redirect, HSTS header) alongside the certbot note.

### L2 — No healthcheck in systemd; no `web/` CI step
- **Where:** `deploy/*.service`, `.github/workflows/`
- **Fix:** add a systemd/`curl` healthcheck note; add a `web/` build+lint job to CI.

### L3 — `{run_id}` path-param defense-in-depth
- **Where:** `src/safedb/api.py:130-138`
- **Note:** Starlette blocks `/` in path params so traversal is prevented today.
- **Fix:** add an explicit `run_id` whitelist check (`isidentifier()`-style) as belt-and-suspenders.
