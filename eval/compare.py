"""Side-by-side comparison table of eval runs (the two experiments + baseline).

    python -m eval.compare                 # latest run per (experiment, split)
    python -m eval.compare <run_id> ...     # specific runs

Every number comes from a committed run.json — never typed by hand.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "eval" / "results"


def load_runs(run_ids: list[str] | None) -> list[dict[str, Any]]:
    if run_ids:
        return [json.loads((RESULTS_DIR / rid / "run.json").read_text()) for rid in run_ids]
    metas = [
        json.loads(Path(p).read_text()) for p in glob.glob(str(RESULTS_DIR / "*" / "run.json"))
    ]
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for meta in sorted(metas, key=lambda m: m.get("date", "")):
        latest[(meta.get("experiment", "?"), meta["split"])] = meta  # keep the newest per key
    return list(latest.values())


def format_table(metas: list[dict[str, Any]]) -> str:
    """Render a markdown comparison table (pure, testable)."""
    header = "| experiment | split | model | exec acc | first-try | recovery | blocked | scored |"
    sep = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, sep]
    for meta in sorted(metas, key=lambda m: (m.get("experiment", ""), m.get("split", ""))):
        m = meta["metrics"]
        lines.append(
            f"| {meta.get('experiment', '?')} | {meta['split']} | {meta.get('model', '?')} "
            f"| {m['execution_accuracy']} | {m['first_try_valid_rate']} | {m['recovery_rate']} "
            f"| {m['blocked_query_rate']} | {m.get('scored', m.get('questions'))} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_ids", nargs="*", help="run ids under eval/results/ (default: latest each)"
    )
    args = parser.parse_args(argv)
    print(format_table(load_runs(args.run_ids or None)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
