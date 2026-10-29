"""Run a split of the Spider slice through the real MCP server and score it.

    python -m eval.run_eval --split tune|holdout --config eval/eval_config.yaml --mode record|replay

Writes eval/results/<run_id>/questions.jsonl (per-question records) and run.json (config, split,
seed, git SHA, tool_descriptions hash, backend, model, date, headline metrics). The gold answer
is never placed in a model request — a leak check asserts this on every call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.score import compute_metrics, find_leak, result_matches
from safedb.config import Settings, load_config
from safedb.llm_client import LLMClient
from safedb.tool_descriptions import descriptions_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
SLICE_PATH = REPO_ROOT / "eval" / "questions" / "slice.jsonl"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
BASELINE_PATH = REPO_ROOT / "eval" / "baseline.json"
SLICE_SEED = 42
MAX_REQUESTS_PER_QUESTION = 6  # question + up to 5 tool-call turns
REGRESSION_TOLERANCE = 0.03  # fail CI if accuracy drops more than 3 points below baseline


class GoldLeak(RuntimeError):
    pass


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _load_split(split: str) -> list[dict[str, Any]]:
    questions = [json.loads(line) for line in SLICE_PATH.read_text().splitlines() if line.strip()]
    return [q for q in questions if q["split"] == split]


async def run(
    split: str,
    config_path: str,
    mode: str,
    force: bool,
    limit: int | None = None,
    gate: bool = False,
) -> str:
    # Imported here so unit tests that import this module don't require mcp / the Agent SDK.
    from eval.claude_runner import answer_question_claude
    from safedb.agent import answer_question
    from safedb.server import ANALYST_PROMPT

    questions = _load_split(split)
    if limit:
        questions = questions[:limit]
    settings = Settings()
    settings.llm_mode = mode
    backend = settings.llm_backend

    run_id = f"{split}-{backend}-{mode}-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    llm = LLMClient(settings, db_path=load_config(config_path).audit_db, run_id=run_id)

    if mode in ("live", "record"):
        if backend == "gemini":
            max_requests = len(questions) * MAX_REQUESTS_PER_QUESTION
            remaining = settings.daily_llm_budget - llm.calls_today()
            print(f"budget: up to {max_requests} Gemini requests needed; {remaining} left today")
            if max_requests > remaining and not force:
                raise SystemExit("would exceed the daily LLM budget; pass --force to override")
        else:
            print("recording on the Claude subscription via the Agent SDK (model: sonnet)")

    records: list[dict[str, Any]] = []
    for q in questions:
        # Leak guard: the gold answer must never appear in anything we author (system + question).
        # The model writing the same SQL or deriving the same result is it being correct, not a
        # leak, so we only inspect our authored content.
        authored = [
            {"role": "system", "content": ANALYST_PROMPT.format(database=q["db"])},
            {"role": "user", "content": q["question"]},
        ]
        reason = find_leak(authored, q["gold_sql"], q["gold_result"])
        if reason:
            raise GoldLeak(f"{q['id']}: {reason}")

        if backend == "claude_sdk":
            result = await answer_question_claude(q["db"], q["question"], config_path, mode)
        else:
            result = await answer_question(llm, q["db"], q["question"], config_path=config_path)

        match = result_matches(result.final_rows, q["gold_result"], q["order_matters"])
        records.append(
            {
                "id": q["id"],
                "db": q["db"],
                "question": q["question"],
                "difficulty": q["difficulty"],
                "scorable": bool(q["gold_result"]),  # empty gold = unscorable (data quirk)
                "steps": [asdict(s) for s in result.steps],
                "final_sql": result.final_sql,
                "match": match,
                "first_try_valid": result.first_try_valid,
                "recovered": result.recovered and match,
                "blocked_count": result.blocked_count,
                "tool_calls": result.tool_calls,
                "latency_ms": result.latency_ms,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "backend": result.backend,
                "model": result.model,
                "reason": result.reason,
            }
        )
        print(f"  {q['id']} [{q['difficulty']}] match={match} tool_calls={result.tool_calls}")

    metrics = compute_metrics(records)
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "questions.jsonl").open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    run_meta = {
        "run_id": run_id,
        "split": split,
        "mode": mode,
        "seed": SLICE_SEED,
        "git_sha": _git_sha(),
        "tool_descriptions_hash": descriptions_hash(),
        "backend": records[0]["backend"] if records else settings.llm_backend,
        "model": records[0]["model"] if records else "",
        "date": datetime.now(UTC).isoformat(),
        "metrics": metrics,
    }
    (out_dir / "run.json").write_text(json.dumps(run_meta, indent=2))

    print(f"\n{run_id}  ->  {out_dir}")
    print(json.dumps(metrics, indent=2))

    if gate:
        baseline = json.loads(BASELINE_PATH.read_text())
        current = metrics["execution_accuracy"]
        base = baseline["execution_accuracy"]
        floor = base - REGRESSION_TOLERANCE
        print(f"\ngate: accuracy {current} vs baseline {base} (floor {floor:.4f})")
        if current < floor:
            raise SystemExit(
                f"REGRESSION: execution accuracy {current} is more than "
                f"{REGRESSION_TOLERANCE} below baseline {baseline['execution_accuracy']}"
            )
        print("gate: OK")
    return run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["tune", "holdout"], default="tune")
    parser.add_argument("--config", default="eval/eval_config.yaml")
    parser.add_argument("--mode", choices=["live", "record", "replay"], default="replay")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--gate", action="store_true", help="fail on >3pt accuracy drop vs baseline"
    )
    args = parser.parse_args(argv)
    asyncio.run(run(args.split, args.config, args.mode, args.force, args.limit, args.gate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
