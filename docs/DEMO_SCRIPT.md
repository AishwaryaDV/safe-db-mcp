# Demo talking points — safe-db-mcp

safe-db-mcp is a tool I built that lets an AI query a real SQL database safely. The model only gets
read-only access, every query is parsed, capped, and logged, and I built an eval harness that
measures how accurate it stays behind that wall. I wrote all of it: the safety layer, the agent
loop, the scoring harness, and the dashboard. AI pair-programmed with me, but the architecture and
the judgment calls were mine.

One thing the AI got wrong: while building the eval, it suggested a change that jumped my accuracy
from 42 to 85 percent. I checked, and it was quietly scoring against the correct answers instead of
the model's own. That is cheating the test, so I threw it out and kept the honest 42.

(Run locally: `make api`, then `npm run dev` in `web/`, then open localhost:3000.)
