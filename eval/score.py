"""Scoring: compare a result to the gold answer, compute metrics, detect gold leaks.

The result-comparison rule (also documented in the README): convert each row to a tuple, round
floats to 4 decimals, treat NULL as None, compare the two result sets as multisets of tuples,
ignore column names, and compare order only when ``order_matters`` is true.

    python -m eval.score --run <run_id>
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "eval" / "results"


def _normalize_cell(value: Any) -> Any:
    return round(value, 4) if isinstance(value, float) else value


def _as_tuples(rows: list[list[Any]] | None) -> list[tuple[Any, ...]]:
    return [tuple(_normalize_cell(v) for v in row) for row in (rows or [])]


def result_matches(
    actual: list[list[Any]] | None, gold: list[list[Any]] | None, order_matters: bool
) -> bool:
    """Compare the model's result to the gold result under the documented rule."""
    a = _as_tuples(actual)
    g = _as_tuples(gold)
    if order_matters:
        return a == g
    return Counter(a) == Counter(g)


def find_leak(messages: Any, gold_sql: str, gold_result: list[list[Any]]) -> str | None:
    """Return a reason string if the gold SQL or gold result appears in the model request.

    Checks the distinctive gold SQL and the exact serialized gold-result array (individual
    values are not checked, to avoid false positives on numbers the model legitimately derives).
    """
    text = json.dumps(messages, default=str)
    if gold_sql and gold_sql in text:
        return "gold_sql present in request"
    if gold_result and json.dumps(gold_result) in text:
        return "gold_result present in request"
    return None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Headline metrics from per-question records (see the eval harness spec)."""
    n = len(records)
    if n == 0:
        return {"questions": 0}

    # A question whose gold_result is empty is unscorable (here: a Spider-mirror whitespace
    # quirk makes the gold join return nothing), so it is excluded from accuracy.
    scorable = [r for r in records if r.get("scorable", True)]
    denom = len(scorable) or 1

    matches = sum(1 for r in scorable if r["match"])
    first_try = sum(1 for r in scorable if r["first_try_valid"])
    failed_first = [r for r in scorable if not r["first_try_valid"]]
    recovered = sum(1 for r in failed_first if r["match"])

    run_query_attempts = sum(
        1 for r in records for step in r["steps"] if step["tool"] == "run_query"
    )
    blocked = sum(r["blocked_count"] for r in records)

    tool_calls = [r["tool_calls"] for r in records]
    latencies = [r["latency_ms"] for r in records]

    by_difficulty: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in scorable:
        by_difficulty[r.get("difficulty", "unknown")].append(r)

    return {
        "questions": n,
        "scored": len(scorable),
        "excluded_unscorable": n - len(scorable),
        "execution_accuracy": round(matches / denom, 4),
        "first_try_valid_rate": round(first_try / denom, 4),
        "recovery_rate": round(recovered / len(failed_first), 4) if failed_first else 0.0,
        "blocked_query_rate": round(blocked / run_query_attempts, 4) if run_query_attempts else 0.0,
        "tool_calls_mean": round(_mean(tool_calls), 2),
        "tool_calls_p95": round(_percentile(tool_calls, 95), 2),
        "latency_ms_mean": round(_mean(latencies), 1),
        "latency_ms_p95": round(_percentile(latencies, 95), 1),
        "tokens_in_mean": round(_mean([r["tokens_in"] for r in records]), 1),
        "tokens_out_mean": round(_mean([r["tokens_out"] for r in records]), 1),
        "accuracy_by_difficulty": {
            d: round(sum(1 for r in rs if r["match"]) / len(rs), 4)
            for d, rs in sorted(by_difficulty.items())
        },
    }


def load_records(run_id: str) -> list[dict[str, Any]]:
    path = RESULTS_DIR / run_id / "questions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    metrics = compute_metrics(load_records(args.run))
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
