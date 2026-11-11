"""Run the ambiguity set through the agent and save transcripts for the owner to score.

    python -m eval.run_ambiguity --mode record

Ambiguous questions have more than one reasonable reading; a good answer asks one clarifying
question or states its assumption. We just save each answer here — the owner reads the
transcripts and marks each good/bad in eval/questions/ambiguity_scores.csv, then runs
`python -m eval.ambiguity_report`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from safedb.config import Settings, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
AMBIGUITY = REPO_ROOT / "eval" / "questions" / "ambiguity.jsonl"
RESULTS_DIR = REPO_ROOT / "eval" / "results"


async def run(config_path: str, mode: str) -> str:
    from eval.claude_runner import answer_question_claude
    from safedb.agent import answer_question
    from safedb.llm_client import LLMClient

    questions = [json.loads(line) for line in AMBIGUITY.read_text().splitlines() if line.strip()]
    settings = Settings()
    settings.llm_mode = mode
    backend = settings.llm_backend
    llm = LLMClient(settings, db_path=load_config(config_path).audit_db)

    transcripts = []
    for q in questions:
        if backend == "claude_sdk":
            result = await answer_question_claude(q["db"], q["question"], config_path, mode)
        else:
            result = await answer_question(llm, q["db"], q["question"], config_path=config_path)
        transcripts.append(
            {
                "id": q["id"],
                "question": q["question"],
                "ambiguity": q["ambiguity"],
                "answer": result.answer,
                "final_sql": result.final_sql,
                "tool_calls": result.tool_calls,
            }
        )
        print(f"  {q['id']}: {q['question'][:50]}")

    run_id = f"ambiguity-{backend}-{mode}-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcripts.jsonl").write_text("\n".join(json.dumps(t) for t in transcripts) + "\n")
    print(f"\nsaved -> {out_dir}/transcripts.jsonl")
    print("Score each good/bad in eval/questions/ambiguity_scores.csv, then:")
    print("  python -m eval.ambiguity_report")
    return run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="eval/eval_config.yaml")
    parser.add_argument("--mode", choices=["live", "record", "replay"], default="record")
    args = parser.parse_args(argv)
    asyncio.run(run(args.config, args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
