"use client";

import { useEffect, useState } from "react";
import { getQuestions, getRuns, type Question, type RunMeta } from "../../lib/api";

function pct(x: number | null | undefined) {
  return x == null ? "—" : `${(x * 100).toFixed(1)}%`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="text-xs uppercase text-stone-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

export default function EvalPage() {
  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRuns()
      .then((r) => {
        setRuns(r.runs);
        if (r.runs[0]) setSelected(r.runs[0].run_id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    getQuestions(selected, filter)
      .then((r) => setQuestions(r.questions))
      .catch((e) => setError(String(e)));
  }, [selected, filter]);

  const run = runs.find((r) => r.run_id === selected);
  const m = run?.metrics ?? {};

  if (error) return <p className="text-sm text-red-600">Could not load eval results ({error}).</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Eval</h1>
        {runs.length > 0 && (
          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            className="rounded border border-stone-300 bg-transparent px-2 py-1 text-sm dark:border-stone-700"
          >
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id} {r.experiment ? `· ${r.experiment}` : ""} ({r.split})
              </option>
            ))}
          </select>
        )}
      </div>

      {run && (
        <>
          <div className="grid gap-4 sm:grid-cols-4">
            <Metric label="Execution accuracy" value={pct(m.execution_accuracy)} />
            <Metric label="First-try valid" value={pct(m.first_try_valid_rate)} />
            <Metric label="Recovered" value={pct(m.recovery_rate)} />
            <Metric label="Blocked" value={m.blocked_total != null ? String(m.blocked_total) : "—"} />
          </div>
          <p className="text-sm text-stone-400">
            {run.model} · {run.date} · scored {m.scored ?? "?"} questions
            {m.excluded_unscorable ? `, ${m.excluded_unscorable} excluded as unscorable` : ""}
          </p>
        </>
      )}

      <div className="flex gap-1">
        {[
          ["", "all"],
          ["match", "passed"],
          ["mismatch", "failed"],
        ].map(([val, label]) => (
          <button
            key={val}
            onClick={() => setFilter(val)}
            className={`rounded px-2 py-1 text-xs ${
              filter === val ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900" : "text-stone-500"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {questions.map((q) => (
          <div key={q.id} className="card">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm">{q.question ?? q.id}</p>
              <span
                className={`pill ${
                  q.match
                    ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                    : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                }`}
              >
                {q.match ? "pass" : "fail"}
              </span>
            </div>
            {q.reason && !q.match && <p className="mt-1 text-xs text-stone-400">{q.reason}</p>}
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <pre className="overflow-x-auto rounded bg-stone-100 p-2 text-xs dark:bg-stone-800">
                <span className="text-stone-400">model</span>
                {"\n"}
                {q.final_sql ?? "(none)"}
              </pre>
              <pre className="overflow-x-auto rounded bg-stone-100 p-2 text-xs dark:bg-stone-800">
                <span className="text-stone-400">gold</span>
                {"\n"}
                {q.gold_sql ?? "(none)"}
              </pre>
            </div>
          </div>
        ))}
        {questions.length === 0 && <p className="text-sm text-stone-400">No questions for this filter.</p>}
      </div>
    </div>
  );
}
