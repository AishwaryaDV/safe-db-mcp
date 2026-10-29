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

### Log Claude in on the server (owner task)

The live `/api/ask` path uses the Claude Agent SDK, which authenticates through the local
Claude Code session. Run once as the `safedb` user so the agent can call the model:

```bash
sudo -u safedb claude login      # or: sudo -u safedb claude  (then /login)
```

Until this is done the backend still serves the cached dashboard pages; only live asks need it.

## Server `.env`

```ini
LLM_BACKEND=claude_sdk              # Claude primary
LLM_MODE=live                       # live model for real questions
GEMINI_API_KEY=...                  # fallback/overflow only (see DECISIONS.md)
ALLOWED_ORIGINS=https://safe-db-mcp.example.com
```

Prod = **Claude primary, Gemini fallback**: if Claude is unavailable or over budget, the
backend quietly falls back to Gemini. Daily caps (10/visitor, 150/global) protect the budget.

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
