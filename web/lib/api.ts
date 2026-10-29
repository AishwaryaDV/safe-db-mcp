// Thin client for the FastAPI backend. Base URL comes from the environment so the same
// build can point at localhost in dev and the real host in prod.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AuditRow = {
  id: number;
  ts: string;
  source: string;
  tool: string;
  database: string | null;
  status: string;
  error_type: string | null;
  sql: string | null;
  row_count: number | null;
  elapsed_ms: number | null;
};

export type RunMeta = {
  run_id: string;
  split: string | null;
  experiment: string | null;
  model: string | null;
  date: string | null;
  metrics: Record<string, number> | null;
};

export type Question = {
  id: string;
  question?: string;
  match: boolean;
  final_sql: string | null;
  gold_sql: string | null;
  reason?: string | null;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const getAudit = (qs = "") => get<{ rows: AuditRow[] }>(`/api/audit${qs}`);
export const getRuns = () => get<{ runs: RunMeta[] }>("/api/eval/runs");
export const getQuestions = (runId: string, result = "") =>
  get<{ questions: Question[] }>(`/api/eval/runs/${runId}/questions${result ? `?result=${result}` : ""}`);
export const getExamples = () => get<{ examples: { database: string; question: string }[] }>("/api/examples");

// SSE events from POST /api/ask, yielded as {event, data} as they arrive.
export async function* askStream(
  database: string,
  question: string,
): AsyncGenerator<{ event: string; data: any }> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ database, question }),
  });
  if (res.status === 429) {
    yield { event: "limit", data: await res.json() };
    return;
  }
  if (!res.ok || !res.body) throw new Error(`ask -> ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const event = chunk.match(/event: (.*)/)?.[1];
      const dataLine = chunk.match(/data: (.*)/)?.[1];
      if (event && dataLine) yield { event, data: JSON.parse(dataLine) };
    }
  }
}
