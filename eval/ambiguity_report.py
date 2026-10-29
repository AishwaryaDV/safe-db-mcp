"""Report the owner's good/bad scores for the ambiguity set.

python -m eval.ambiguity_report
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCORES = REPO_ROOT / "eval" / "questions" / "ambiguity_scores.csv"


def tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count non-empty good/bad scores (pure, testable)."""
    return dict(Counter(r["score"].strip().lower() for r in rows if r.get("score", "").strip()))


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    rows = list(csv.DictReader(SCORES.open()))
    counts = tally(rows)
    scored = sum(counts.values())
    good = counts.get("good", 0)
    pct = f"{round(100 * good / scored)}%" if scored else "n/a (not scored yet)"
    print(f"ambiguity: {good}/{scored} good — {pct}")
    print(counts)
    if scored < len(rows):
        print(f"({len(rows) - scored} of {len(rows)} not yet scored in {SCORES.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
