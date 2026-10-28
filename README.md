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

## Use it in Claude Desktop

Add the server to Claude Desktop's config file
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS). Use **absolute
paths**, since the client launches the server from its own working directory:

```json
{
  "mcpServers": {
    "safe-db-mcp": {
      "command": "/ABSOLUTE/PATH/TO/safe-db-mcp/.venv/bin/safedb-mcp",
      "args": ["--config", "/ABSOLUTE/PATH/TO/safe-db-mcp/config.yaml"]
    }
  }
}
```

Set the Chinook `path` in `config.yaml` to an absolute path too, then restart Claude Desktop.
It will list the four tools; ask questions in plain English and it writes the SQL for you.

Five questions to try against Chinook:

1. How many tracks are in the database?
2. Who are the top 5 artists by number of albums?
3. Which 5 countries have the most customers?
4. What are the 5 longest tracks, with their album titles?
5. What is the total revenue by billing country (top 5)?

A dangerous request (e.g. "delete the Album table") is refused by the server, not the model.

<!-- Demo GIF added in the final capture pass. -->

## Licence

MIT. See [`LICENSE`](LICENSE). Bundled data (Chinook, Spider) is downloaded locally and never
committed; see [`DATA_SOURCES.md`](DATA_SOURCES.md).
