"use client";

import { useEffect, useState } from "react";
import { getAudit, type AuditRow } from "../../lib/api";

const STATUS = ["", "ok", "blocked", "error"];

function statusPill(status: string) {
  const color =
    status === "ok"
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : status === "blocked"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
        : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  return <span className={`pill ${color}`}>{status}</span>;
}

export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    getAudit(status ? `?status=${status}` : "")
      .then((r) => setRows(r.rows))
      .catch((e) => setError(String(e)));
  }, [status]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Audit log</h1>
        <div className="flex gap-1">
          {STATUS.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded px-2 py-1 text-xs ${
                status === s ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900" : "text-stone-500"
              }`}
            >
              {s || "all"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">Could not load the audit log ({error}).</p>}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-stone-200 text-xs uppercase text-stone-400 dark:border-stone-800">
            <tr>
              <th className="p-3">Time</th>
              <th className="p-3">Tool</th>
              <th className="p-3">DB</th>
              <th className="p-3">Status</th>
              <th className="p-3">SQL</th>
              <th className="p-3">Rows</th>
              <th className="p-3">ms</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-stone-100 align-top dark:border-stone-800/50">
                <td className="whitespace-nowrap p-3 text-stone-400">{r.ts?.slice(0, 19).replace("T", " ")}</td>
                <td className="p-3 font-mono text-xs">{r.tool}</td>
                <td className="p-3">{r.database}</td>
                <td className="p-3">
                  {statusPill(r.status)}
                  {r.error_type && <div className="mt-1 text-xs text-stone-400">{r.error_type}</div>}
                </td>
                <td className="max-w-md p-3 font-mono text-xs text-stone-500">{r.sql}</td>
                <td className="p-3">{r.row_count}</td>
                <td className="p-3 text-stone-400">{r.elapsed_ms}</td>
              </tr>
            ))}
            {rows.length === 0 && !error && (
              <tr>
                <td colSpan={7} className="p-6 text-center text-stone-400">
                  No entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
