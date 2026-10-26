# Related work (P1b)

How other database-MCP servers enforce read-only, read from their **source** (not just their
READMEs) on 2026-10-26. The point of this exercise is to turn their checks into tests before
we write our own safety layer (P2), and to make sure any "difference" we later claim in the
README is backed by a row here.

Projects read (shallow-cloned and inspected):

| Project | Language | Key files read | SQLite? |
| --- | --- | --- | --- |
| [mcp-sqlite-readonly](https://github.com/Fanom2813/mcp-sqlite-readonly) | Node | `mcp-sqlite-server.js` (single file) | **Yes** (SQLite-only) |
| [Postgres MCP Pro](https://github.com/crystaldba/postgres-mcp) | Python | `src/postgres_mcp/sql/safe_sql.py`, `sql/sql_driver.py`, `server.py` | **No** (Postgres-only) |
| [DBHub](https://github.com/bytebase/dbhub) | TypeScript | `src/utils/allowed-keywords.ts`, `utils/sql-parser.ts`, `tools/execute-sql.ts`, `connectors/sqlite/index.ts`, `utils/sql-row-limiter.ts`, `utils/query-timeout.ts` | **Yes** (`connectors/sqlite/`) |

Google's MCP Toolbox for Databases was intentionally skipped: it is a Go "mediated access"
toolbox rather than a SQL-validation server, and is not SQLite-focused.

> **SQLite support is not a difference.** DBHub and mcp-sqlite-readonly both support SQLite,
> so we never claim SQLite support as something only this project does.

## How each enforces read-only (plain words + file)

**mcp-sqlite-readonly** — string-based, one file.
- Opens the database with `SQLITE_OPEN_READONLY` (`mcp-sqlite-server.js:30`).
- Strips `/* */` and `--` comments by regex, uppercases, normalises whitespace
  (`:156-161`).
- Splits on `;` into statements (`:175`) — a **naive split** that does not account for a
  semicolon inside a string literal.
- Allow-lists statements that start with `SELECT` / `EXPLAIN` / `WITH` (`:178-191`).
- Blacklists keywords by word-boundary regex: `INSERT, UPDATE, DELETE, CREATE, DROP, ALTER,
  TRUNCATE, REPLACE, ATTACH, DETACH, PRAGMA, REINDEX, VACUUM, ANALYZE` (`:194-212`).
- Its structured `read_records` tool validates table/column identifiers and binds parameters
  (`validateTableName`, `:79`).
- **No** real parser, **no** SQLite authorizer, **no** statement timeout, **no** audit log.

**Postgres MCP Pro** — real parser, Postgres only.
- Read-only is an **opt-in** mode: `AccessMode` defaults to `UNRESTRICTED`; `RESTRICTED` is
  "read-only with safety features" (`server.py:49-70`, default `UNRESTRICTED` at `:58`).
- In restricted mode, `SafeSqlDriver` parses with **`pglast`** and allow-lists statement
  *types* (`SelectStmt`, `ExplainStmt`, `VariableShowStmt`, `VacuumStmt`/ANALYZE, cursor
  statements), rejecting all DDL/DML, with deep tree validation (`sql/safe_sql.py:89-120+`).
- Execution runs inside **`BEGIN TRANSACTION READ ONLY`** (`sql/sql_driver.py:231`), so an
  allowed statement cannot escape read-only; a 30s timeout is applied (`server.py:68`).
- **No** audit log.

**DBHub** — keyword-based, multi-database (incl. SQLite).
- Per-tool `readonly` policy; a violation returns `READONLY_VIOLATION`
  (`tools/execute-sql.ts:54-58`).
- Allow-list per connector; **SQLite = `select, with, explain, pragma`** — i.e. it *allows*
  `PRAGMA` for SQLite (`utils/allowed-keywords.ts`). A `mutatingKeywords` regex
  (`insert/update/delete/drop/alter/create/truncate/merge/grant/revoke/rename`) catches DML
  hidden in CTEs.
- Comments and string literals are stripped before classification
  (`utils/sql-parser.ts`, `stripCommentsAndStrings`), explicitly to stop
  `SELECT 1--1;DROP TABLE t` style tricks.
- SQLite is opened with node:sqlite `readOnly` when configured and not `:memory:`
  (`connectors/sqlite/index.ts:186-195`).
- Row cap uses a **`maxRows + 1` probe** with truncation detection
  (`utils/sql-row-limiter.ts`) — the same technique this project uses.
- Statement timeout is enforced **only for the pooled server engines** (Postgres/MySQL/
  MariaDB), *not* SQLite (`utils/query-timeout.ts`).
- **No** SQLite authorizer, **no** audit log.

## Check-by-check comparison

Legend: ✓ present · ✗ absent · n/a not applicable (Postgres-only). The last column is this
project's mechanism and the matching hostile-query test number(s).

| Check | DBHub | Postgres MCP Pro | mcp-sqlite-readonly | This project (test #) |
| --- | --- | --- | --- | --- |
| Open connection read-only | ✓ node:sqlite `readOnly` | ✓ `BEGIN TRANSACTION READ ONLY` | ✓ `SQLITE_OPEN_READONLY` | ✓ `mode=ro` + `PRAGMA query_only` (always on) |
| Real AST parse (for SQLite) | ✗ keyword/regex | ✓ `pglast` (Postgres only) | ✗ keyword/regex | ✓ `sqlglot` SQLite dialect |
| Allow-list read statements | ✓ | ✓ (statement types) | ✓ SELECT/EXPLAIN/WITH | ✓ SELECT/WITH/set-ops (#20) |
| Reject DML/DDL | ✓ | ✓ | ✓ | ✓ (#1–7, #14) |
| Comment-injection guard | ✓ strip | ✓ parser | ✓ regex strip | ✓ parser (#11, #12) |
| Multi-statement rejected | ✓ strip + detect | ✓ parser | ~ naive `split(';')` | ✓ "exactly one statement" (#9, #10, #13) |
| Block `PRAGMA` | ✗ (allows for SQLite) | n/a | ✓ | ✓ (#15, #16) |
| Block `ATTACH` | ~ | n/a | ✓ (ATTACH + DETACH) | ✓ (#17) |
| Block `DETACH` | ~ | n/a | ✓ | ✗ → **add #39** |
| Block transaction control (BEGIN/COMMIT/ROLLBACK) | ~ | ✓ (escape guard) | ~ (not in blacklist) | allow-list rejects, untested → **add #33–#36** |
| Block `REINDEX` / `ANALYZE` (SQLite writes) | ~ | ANALYZE allowed (safe in PG) | ✓ | allow-list rejects, untested → **add #37, #38** |
| Block dangerous functions (`load_extension`, `readfile`) | ✗ | n/a | ~ (relies on read-only) | ✓ explicit deny (#18, #19) |
| Row cap + truncation flag | ✓ `maxRows+1` | ✗ | ~ limit/offset validation | ✓ `max_rows+1` (#23, #24) |
| Statement timeout on SQLite | ✗ (server engines only) | ✓ (Postgres, 30s) | ✗ | ✓ progress handler (#21, #22) |
| SQLite authorizer (second wall) | ✗ | n/a | ✗ | ✓ authorizer callback |
| Audit log of every call incl. blocked | ✗ | ✗ | ✗ | ✓ `audit_log` (#31) |
| Published hostile-query test table | ✗ | ✗ (has tests, no published table) | ✗ | ✓ (this suite) |
| Accuracy measured through MCP on a public benchmark | ✗ | ✗ | ✗ | ✓ (Spider eval) |

## Gaps we are adding as tests (32 + 8)

SQLite accepts each of these and our allow-list already rejects them, but the 32-test list had
no explicit proof. Added after this comparison; runnable tests are written in P2 (tests-first).

| New # | Input | Expected | Prompted by |
| --- | --- | --- | --- |
| 33 | `BEGIN` | blocked | PG MCP Pro transaction-escape guard |
| 34 | `COMMIT` | blocked | PG MCP Pro transaction-escape guard |
| 35 | `ROLLBACK` | blocked | PG MCP Pro transaction-escape guard |
| 36 | `SAVEPOINT s1` (and `RELEASE s1`) | blocked | PG MCP Pro transaction-escape guard |
| 37 | `REINDEX` | blocked | mcp-sqlite-readonly blacklist (writes in SQLite) |
| 38 | `ANALYZE` | blocked | mcp-sqlite-readonly blacklist (writes `sqlite_stat*`) |
| 39 | `DETACH DATABASE x` | blocked | mcp-sqlite-readonly blocks ATTACH + DETACH |
| 40 | `SELECT ';' ; DROP TABLE Album` | blocked (two statements) | beats mcp-sqlite-readonly's naive `split(';')` |

## Differences this project may claim in the README

Only rows whose verdict is "only this project," verified above. **SQLite support** and a
**row cap on SQLite** are deliberately excluded (DBHub has both).

| Difference | Verdict |
| --- | --- |
| Audit log of every call, including blocked ones | **Only this project** — none of the three logs calls |
| SQLite authorizer as a second wall behind the parser | **Only this project** — DBHub uses the node:sqlite read-only flag, not an authorizer; mcp-sqlite-readonly has none |
| Statement timeout on SQLite | **Only this project** — DBHub times out server engines only; mcp-sqlite-readonly has none |
| AST-level validation for SQLite (`sqlglot`) | **Only this project** — DBHub and mcp-sqlite-readonly are keyword/regex based for SQLite; Postgres MCP Pro parses but is Postgres-only |
| Published hostile-query test table | **Only this project** |
| Accuracy measured through the MCP interface on a public benchmark | **Only this project** |
| SQLite support | Not a difference (DBHub, mcp-sqlite-readonly) |
| Row cap on SQLite | Not a difference (DBHub) |
