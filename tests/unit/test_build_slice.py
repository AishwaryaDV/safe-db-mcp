"""Pure-logic tests for the Spider slice builder (no network, synthetic DB)."""

import sqlite3

import pytest
from eval.build_slice import choose_slice, classify_hardness, compute_gold, order_matters


@pytest.mark.unit
def test_classify_hardness_scales_with_sql_shape():
    assert classify_hardness("SELECT * FROM t") == "easy"
    assert classify_hardness("SELECT count(*) FROM t WHERE x > 1") == "medium"
    hard = (
        "SELECT a, count(*) FROM t JOIN u ON t.id = u.id WHERE x > 1 GROUP BY a HAVING count(*) > 2"
    )
    assert classify_hardness(hard) in ("hard", "extra")


@pytest.mark.unit
def test_order_matters():
    assert order_matters("SELECT * FROM t ORDER BY x") is True
    assert order_matters("SELECT * FROM t") is False


@pytest.mark.unit
def test_compute_gold_normalizes(tmp_path):
    path = tmp_path / "t.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE t (x REAL, y TEXT);INSERT INTO t (x, y) VALUES (1.123456, 'a'), (2.0, NULL);"
    )
    conn.commit()
    conn.close()

    rows = compute_gold(path, "SELECT x, y FROM t ORDER BY x")
    assert rows == [[1.1235, "a"], [2.0, None]]  # float rounded to 4 dp, NULL -> None


def _synthetic_rows(n=120):
    rows = []
    sqls = {
        "easy": "SELECT * FROM t",
        "medium": "SELECT count(*) FROM t WHERE x > 1",
        "hard": "SELECT a FROM t JOIN u ON t.id = u.id WHERE x > 1 GROUP BY a ORDER BY a",
    }
    difficulties = list(sqls)
    for i in range(n):
        d = difficulties[i % len(difficulties)]
        rows.append(
            {"db": f"db{i % 8}", "gold_sql": sqls[d], "question": f"q{i}?", "difficulty": d}
        )
    return rows


@pytest.mark.unit
def test_choose_slice_counts_and_splits():
    chosen = choose_slice(_synthetic_rows(), seed=42, n_total=50, tune=30)
    assert len(chosen) == 50
    assert sum(1 for r in chosen if r["split"] == "tune") == 30
    assert sum(1 for r in chosen if r["split"] == "holdout") == 20
    assert len({r["db"] for r in chosen}) >= 5  # at least 5 databases
    assert len({r["difficulty"] for r in chosen}) >= 2  # mixed difficulty
    assert [r["id"] for r in chosen][:3] == ["q001", "q002", "q003"]


@pytest.mark.unit
def test_choose_slice_is_deterministic():
    a = choose_slice(_synthetic_rows(), seed=42)
    b = choose_slice(_synthetic_rows(), seed=42)
    assert a == b
    c = choose_slice(_synthetic_rows(), seed=7)
    assert [r["question"] for r in a] != [r["question"] for r in c]
