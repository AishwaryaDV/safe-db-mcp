# safe-db-mcp

An MCP server that lets an AI client query **SQLite** databases **safely** — every query
validated, forced read-only, row-capped, time-limited, and logged — plus an eval harness that
measures how accurately a model answers benchmark questions through the server.

> Work in progress. This README is expanded to the full standard (demo GIF, live link,
> results tables, failure write-ups) in the final phase. For now:
>
> - [`docs/USAGE.md`](docs/USAGE.md) — install and usage
> - [`docs/PROJECT_A.md`](docs/PROJECT_A.md) — full specification
> - [`docs/VERIFY.md`](docs/VERIFY.md) — per-phase verification checklist

## Quick start

```bash
make setup     # create the virtualenv, install the package, download Chinook
make run       # start the MCP server over stdio
make test      # run the test suite
make lint      # ruff lint + format check
```

## Licence

MIT. See [`LICENSE`](LICENSE). Bundled data (Chinook, Spider) is downloaded locally and never
committed; see [`DATA_SOURCES.md`](DATA_SOURCES.md).
