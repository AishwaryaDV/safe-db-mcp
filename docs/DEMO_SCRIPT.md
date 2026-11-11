# Demo script — safe-db-mcp (~2.5 min)

## Before you start (one terminal each)
```
cd ~/Desktop/safe-db-mcp && make api          # API on :8000
cd ~/Desktop/safe-db-mcp/web && npm run dev    # dashboard on :3000
```
Open **http://localhost:3000**. (Backend is set to your Claude login, so "Try it" answers live.)

---

## What you say

**[On the Overview page]**

"This is safe-db-mcp. It lets an AI query a real SQL database without being able to break
anything. The model only gets read-only access, every query is checked, capped, and logged — and
I actually measured how accurate it stays behind that wall."

**[Click "Try it". Click the chip: "Who are the top 5 artists by number of albums?"]**

"So I ask in plain English. The model looks at the schema, writes the SQL itself, and runs it
through my server. Watch the trace — you can see each tool call stream in live, then the answer
and the real rows come back."

**[Let it finish. Point at the SQL and the result table.]**

"If it writes a bad query, or tries a table that doesn't exist, the server blocks it and hands
back a hint, and the model fixes itself. It physically can't write, drop, or reach anything
outside these tables — that's enforced on the server, not trusted to the model."

**[Click "Eval".]**

"Now the honest part. I didn't just build it, I tested it. This runs real benchmark questions
through the whole system and checks the answers against known-correct results. It lands around
42 percent, and I can show you exactly which questions passed and which failed — the model's SQL
right next to the correct one. No cherry-picking."

**[Click a failed one to show the side-by-side. Then click "Audit log".]**

"And everything's logged here — every query the server saw, including the blocked ones, with
timing. If you ever wonder what the AI actually did, it's all in one place."

**[Back to Overview.]**

"The whole thing is self-hostable, and whoever runs it brings their own API key — nothing's baked
in. That's it: a safe, auditable, and measured way to put an AI in front of a database."

---

## If asked
- **"Which models?"** — Claude or Gemini; you pick in config and supply your own key. Claude is primary, Gemini is the fallback.
- **"Is 42% good?"** — It's an honest baseline on a hard benchmark (Spider), and it's reproducible with no key via a committed cache. The point is measuring it at all, and being able to improve it.
- **"What stops SQL injection / a destructive query?"** — Two walls: the query is parsed and only read-only statements are allowed, and the database connection itself is opened read-only. Blocked attempts still get logged.
- **If "Try it" is slow (~8s):** that's the model thinking; the example chips run the same live path.
