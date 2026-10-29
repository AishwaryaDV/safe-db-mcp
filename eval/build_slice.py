"""Build the 50-question Spider slice with gold results.

Pure, model-free: picks questions with a fixed seed, computes each one's gold result by
running its gold SQL against the real Spider database (read-only), splits 30 tune / 20 holdout,
and writes ``eval/questions/slice.jsonl``. Also writes ``eval/eval_config.yaml`` so the MCP
server can open the chosen Spider databases during the eval (the main ``config.yaml`` stays
chinook-only). Databases are fetched per-file from ``premai-io/spider`` on demand.

    python -m eval.build_slice [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from safedb import db
from safedb.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
QUESTIONS_DIR = REPO_ROOT / "eval" / "questions"
EVAL_CONFIG = REPO_ROOT / "eval" / "eval_config.yaml"
SPIDER_DB_REPO = "premai-io/spider"

_AGG = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
_COMPONENT_KEYWORDS = (
    "where",
    "group by",
    "order by",
    "having",
    "limit",
    "join",
    "union",
    "intersect",
    "except",
)


def classify_hardness(sql: str) -> str:
    """A lightweight Spider-style hardness estimate from the gold SQL's shape."""
    lowered = f" {sql.lower()} "
    components = sum(1 for kw in _COMPONENT_KEYWORDS if f" {kw} " in lowered)
    components += len(_AGG.findall(sql))
    components += max(sql.lower().count("select") - 1, 0)  # subqueries
    if components <= 1:
        return "easy"
    if components <= 3:
        return "medium"
    if components <= 5:
        return "hard"
    return "extra"


def order_matters(sql: str) -> bool:
    return "order by" in sql.lower()


def _normalize(value: Any) -> Any:
    return round(value, 4) if isinstance(value, float) else value


def compute_gold(db_path: str | Path, sql: str) -> list[list[Any]]:
    """Run the gold SQL read-only and return rows as lists (floats rounded, NULL as None)."""
    conn = db.open_readonly(db_path)
    try:
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    return [[_normalize(v) for v in row] for row in rows]


def choose_slice(
    rows: list[dict[str, Any]], seed: int, n_total: int = 50, tune: int = 30
) -> list[dict[str, Any]]:
    """Deterministically pick n_total questions, round-robin across difficulty for a mix.

    First ``tune`` go to the tune split, the rest to holdout. Pure (no DB access).
    """
    rng = random.Random(seed)
    pool = list(rows)
    rng.shuffle(pool)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        buckets[row["difficulty"]].append(row)

    order = ["easy", "medium", "hard", "extra"]
    chosen: list[dict[str, Any]] = []
    while len(chosen) < n_total and any(buckets[d] for d in order):
        for difficulty in order:
            if len(chosen) >= n_total:
                break
            if buckets[difficulty]:
                chosen.append(buckets[difficulty].pop())

    result = []
    for i, row in enumerate(chosen):
        result.append(
            {
                "id": f"q{i + 1:03d}",
                "db": row["db"],
                "question": row["question"],
                "gold_sql": row["gold_sql"],
                "difficulty": row["difficulty"],
                "split": "tune" if i < tune else "holdout",
            }
        )
    return result


def _ensure_db(name: str) -> Path:
    from huggingface_hub import hf_hub_download

    dest = DATA_DIR / "spider" / "database" / name / f"{name}.sqlite"
    if dest.exists():
        return dest
    cached = hf_hub_download(SPIDER_DB_REPO, f"database/{name}/{name}.sqlite", repo_type="dataset")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, dest)
    return dest


def _write_eval_config(dbs_used: list[str]) -> None:
    base = load_config(REPO_ROOT / "config.yaml")
    databases = [d.model_dump() for d in base.databases]
    for name in dbs_used:
        databases.append(
            {
                "name": name,
                "path": f"data/spider/database/{name}/{name}.sqlite",
                "description": f"Spider benchmark database: {name}",
            }
        )
    data = {
        "databases": databases,
        "limits": base.limits.model_dump(),
        "audit_db": base.audit_db,
    }
    EVAL_CONFIG.write_text(yaml.safe_dump(data, sort_keys=False))


def build(seed: int = 42, n_total: int = 50, tune: int = 30) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    dev = DATA_DIR / "spider" / "dev.parquet"
    if not dev.exists():
        raise SystemExit("run `python scripts/download_data.py --dataset spider` first")

    table = pq.read_table(dev, columns=["db_id", "query", "question"])
    rows = [
        {"db": d, "gold_sql": q, "question": qn, "difficulty": classify_hardness(q)}
        for d, q, qn in zip(
            table.column("db_id").to_pylist(),
            table.column("query").to_pylist(),
            table.column("question").to_pylist(),
            strict=True,
        )
    ]

    chosen = choose_slice(rows, seed, n_total, tune)
    dbs_used = sorted({r["db"] for r in chosen})
    db_paths = {name: _ensure_db(name) for name in dbs_used}

    QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    slice_path = QUESTIONS_DIR / "slice.jsonl"
    records = []
    with slice_path.open("w") as f:
        for row in chosen:
            record = {
                "id": row["id"],
                "db": row["db"],
                "question": row["question"],
                "gold_sql": row["gold_sql"],
                "gold_result": compute_gold(db_paths[row["db"]], row["gold_sql"]),
                "order_matters": order_matters(row["gold_sql"]),
                "difficulty": row["difficulty"],
                "split": row["split"],
            }
            f.write(json.dumps(record) + "\n")
            records.append(record)

    _write_eval_config(dbs_used)

    by_difficulty = Counter(r["difficulty"] for r in records)
    by_split = Counter(r["split"] for r in records)
    print(f"build_slice: wrote {len(records)} questions over {len(dbs_used)} databases")
    print(f"  difficulty: {dict(by_difficulty)}")
    print(f"  split: {dict(by_split)}")
    print(f"  -> {slice_path}")
    print(f"  -> {EVAL_CONFIG}")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    build(seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
