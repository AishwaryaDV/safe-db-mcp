# Deploying safe-db-mcp

Self-hosted on Ubuntu + nginx. Two processes sit behind nginx: the FastAPI backend
(`/api`) and the Next.js dashboard (`/`). The backend answers live questions through the
Claude Agent SDK, which uses the **Claude Code login on the server** — no API key.

## Layout

```
/opt/safe-db-mcp            # this repo
  .venv/                    # Python venv (backend)
  .env                      # server secrets + switches (NOT in git)
  data/audit.sqlite         # audit log + api_requests (created on first run)
  web/                      # Next.js app (built in place)
```

## One-time setup

```bash
sudo adduser --system --group safedb
sudo git clone <repo> /opt/safe-db-mcp && cd /opt/safe-db-mcp
sudo chown -R safedb:safedb /opt/safe-db-mcp

# Backend
python3 -m venv .venv && .venv/bin/pip install -e .

# Dashboard (point it at the public host, then build)
cd web && echo "NEXT_PUBLIC_API_URL=https://safe-db-mcp.example.com" > .env.local
npm ci && npm run build && cd ..
```

### Pick a model backend (bring your own key)

The live `/api/ask` path needs a model. For a hosted instance use `anthropic_api` with your own
Anthropic key (below) — do not ship anyone else's key. Alternatively `gemini` with a Gemini key.
`claude_sdk` (a local `claude login`, no key) is for local dev only, not a server.

## Server `.env`

```ini
LLM_BACKEND=anthropic_api           # your own key; falls back to Gemini on error/budget
LLM_MODE=live                       # live model for real questions
ANTHROPIC_API_KEY=...               # the host's key — lives only here, never committed
GEMINI_API_KEY=...                  # optional fallback
ALLOWED_ORIGINS=https://safe-db-mcp.example.com
```

If `ANTHROPIC_API_KEY` is unavailable or over budget, the backend quietly falls back to Gemini.
Daily caps (10/visitor, 150/global) protect the budget. Leave the key blank and the read-only
dashboard pages (eval, audit) still serve; only live asks need it.

## Services + proxy

```bash
sudo cp deploy/safe-db-mcp-api.service deploy/safe-db-mcp-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now safe-db-mcp-api safe-db-mcp-web

sudo cp deploy/nginx.conf /etc/nginx/sites-available/safe-db-mcp
sudo ln -s /etc/nginx/sites-available/safe-db-mcp /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d safe-db-mcp.example.com    # TLS
```

## Updating

```bash
cd /opt/safe-db-mcp && git pull
.venv/bin/pip install -e .                 # if deps changed
cd web && npm ci && npm run build && cd ..  # if the dashboard changed
sudo systemctl restart safe-db-mcp-api safe-db-mcp-web
```
