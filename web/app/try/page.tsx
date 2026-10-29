"use client";

import { useEffect, useRef, useState } from "react";
import { askStream, getExamples } from "../../lib/api";

type Trace =
  | { kind: "tool_call"; tool: string; args: any }
  | { kind: "tool_result"; tool: string; ok: boolean; error_type: string | null };

type Final = {
  answer: string;
  final_sql: string | null;
  columns: string[] | null;
  rows: any[][] | null;
};

export default function TryPage() {
  const [examples, setExamples] = useState<{ database: string; question: string }[]>([]);
  const [question, setQuestion] = useState("");
  const [trace, setTrace] = useState<Trace[]>([]);
  const [final, setFinal] = useState<Final | null>(null);
  const [limit, setLimit] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const traceEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getExamples().then((r) => setExamples(r.examples)).catch(() => {});
  }, []);
  useEffect(() => {
    traceEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [trace, final]);

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true);
    setTrace([]);
    setFinal(null);
    setLimit(null);
    setError(null);
    try {
      for await (const { event, data } of askStream("chinook", q)) {
        if (event === "tool_call") setTrace((t) => [...t, { kind: "tool_call", ...data }]);
        else if (event === "tool_result") setTrace((t) => [...t, { kind: "tool_result", ...data }]);
        else if (event === "final") setFinal(data);
        else if (event === "limit") setLimit(data);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Try it</h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about the chinook music store database…"
          className="flex-1 rounded border border-stone-300 bg-transparent px-3 py-2 text-sm dark:border-stone-700"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-stone-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900"
        >
          {busy ? "Thinking…" : "Ask"}
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        {examples.map((ex) => (
          <button
            key={ex.question}
            onClick={() => {
              setQuestion(ex.question);
              ask(ex.question);
            }}
            className="rounded-full border border-stone-300 px-3 py-1 text-xs text-stone-500 hover:border-stone-500 dark:border-stone-700"
          >
            {ex.question}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">Something went wrong ({error}).</p>}

      {limit && (
        <div className="card border-amber-300 bg-amber-50 text-sm dark:border-amber-800 dark:bg-amber-950">
          <p className="font-medium">{limit.message}</p>
          <p className="mt-1 text-stone-500">Try one of the example questions above — those are cached.</p>
        </div>
      )}

      {(trace.length > 0 || busy) && (
        <div className="card space-y-2">
          <div className="text-xs uppercase text-stone-400">What the agent did</div>
          {trace.map((t, i) =>
            t.kind === "tool_call" ? (
              <div key={i} className="font-mono text-xs">
                <span className="text-stone-400">→ {t.tool}</span>
                {t.args?.sql && <pre className="mt-1 overflow-x-auto rounded bg-stone-100 p-2 dark:bg-stone-800">{t.args.sql}</pre>}
              </div>
            ) : (
              <div key={i} className="font-mono text-xs text-stone-400">
                {t.ok ? "ok" : `blocked (${t.error_type})`}
              </div>
            ),
          )}
          <div ref={traceEnd} />
        </div>
      )}

      {final && (
        <div className="space-y-3">
          <div className="card">
            <div className="text-xs uppercase text-stone-400">Answer</div>
            <p className="mt-1">{final.answer}</p>
          </div>
          {final.final_sql && (
            <pre className="overflow-x-auto rounded bg-stone-100 p-3 font-mono text-xs dark:bg-stone-800">{final.final_sql}</pre>
          )}
          {final.rows && final.rows.length > 0 && (
            <div className="card overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                {final.columns && (
                  <thead className="border-b border-stone-200 text-xs uppercase text-stone-400 dark:border-stone-800">
                    <tr>
                      {final.columns.map((c) => (
                        <th key={c} className="p-2">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {final.rows.map((row, i) => (
                    <tr key={i} className="border-b border-stone-100 dark:border-stone-800/50">
                      {row.map((cell, j) => (
                        <td key={j} className="p-2 font-mono text-xs">
                          {String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
