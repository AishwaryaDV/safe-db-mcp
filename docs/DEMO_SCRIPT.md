# Demo script — safe-db-mcp (~2.5 min)

## Before you start
Run it locally in two terminals: `make api` from the repo root (API on :8000), and `npm run dev`
from `web/` (dashboard on :3000). Then open http://localhost:3000. The backend is set to your
Claude login, so "Try it" answers live with no key and no API cost.

---

## What you say

**[On the Overview page]**

"This is safe-db-mcp, a recent AI product I built. It lets an AI query a real SQL database without
being able to break anything — read-only access only, every query checked, capped, and logged —
and I measured how accurate it stays behind that wall. I built all of it myself: the safety layer,
the agent loop, the eval that scores it, and this dashboard. AI pair-programmed with me, but the
architecture and the hard calls were mine."

**[Click "Try it". Click the chip: "Who are the top 5 artists by number of albums?"]**

"I ask in plain English. The model reads the schema, writes the SQL itself, and runs it through my
server. Watch the trace stream in live — each tool call, then the answer and the real rows. If it
writes a bad query, or names a table that doesn't exist, the server blocks it and hands back a
hint, and the model corrects itself. It physically can't write, drop, or touch anything outside
these tables."

**[Click "Eval".]**

"Now the honest part — I didn't just build it, I tested it. Real benchmark questions run through
the whole system, answers checked against known-correct results. It lands around 42 percent. And
here's the one time AI got it wrong on me: while building this eval, the assistant suggested a
change that jumped the score from 42 to 85. Looked amazing — until I checked and saw it was scoring
against the correct answers instead of the model's. That's not a better model, that's cheating the
test. I threw it out and kept the honest 42. I can show you every question that passed or failed,
model's SQL next to the right one."

**[Click a failed one to show the side-by-side. Then click "Audit log".]**

"Everything's logged here too — every query the server saw, including the blocked ones, with
timing. If you ever wonder what the AI actually did, it's all here."

**[Back to Overview.]**

"It's self-hostable, and whoever runs it brings their own API key — nothing's baked in. A safe,
auditable, measured way to put an AI in front of a database."

---

## If asked
- **"Which models?"** — Claude or Gemini; you pick in config and bring your own key. Claude primary, Gemini fallback.
- **"Is 42% good?"** — Honest baseline on a hard benchmark (Spider), reproducible with no key via a committed cache. The point is measuring it and being able to improve it.
- **"What stops a destructive query / SQL injection?"** — Two walls: the query is parsed and only read-only statements are allowed, and the DB connection itself is opened read-only. Blocked attempts still get logged.
- **If "Try it" is slow (~8s):** that's the model thinking; the example chips run the same live path.
