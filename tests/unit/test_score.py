"""Result-comparison rule (>=10 cases), metrics, and the gold-leak detector."""

import pytest
from eval.score import compute_metrics, find_leak, result_matches


@pytest.mark.unit
@pytest.mark.parametrize(
    "actual, gold, order_matters, expected",
    [
        ([[1], [2]], [[1], [2]], False, True),  # 1 identical
        ([[2], [1]], [[1], [2]], False, True),  # 2 same rows, order ignored
        ([[2], [1]], [[1], [2]], True, False),  # 3 order matters -> mismatch
        ([[1.123456]], [[1.1235]], False, True),  # 4 float rounded to 4 dp
        ([[None]], [[None]], False, True),  # 5 NULL as None
        ([[1]], [[2]], False, False),  # 6 different value
        ([[1], [2]], [[1]], False, False),  # 7 different row count
        ([], [], False, True),  # 8 both empty
        ([], [[1]], False, False),  # 9 empty vs non-empty
        ([[1], [1]], [[1]], False, False),  # 10 multiset: duplicate counts matter
        ([["a", "b"]], [["b", "a"]], False, False),  # 11 column order within a row matters
        ([[1], [2]], [[1], [2]], True, True),  # 12 order matters, same order
    ],
)
def test_result_matches(actual, gold, order_matters, expected):
    assert result_matches(actual, gold, order_matters) is expected


@pytest.mark.unit
def test_find_leak_detects_gold_sql():
    messages = [{"role": "user", "content": "the answer is SELECT count(*) FROM singer"}]
    assert find_leak(messages, "SELECT count(*) FROM singer", [[4]]) is not None


@pytest.mark.unit
def test_find_leak_detects_gold_result_array():
    messages = [{"role": "user", "content": "here: [[42]]"}]
    assert find_leak(messages, "SELECT x FROM t", [[42]]) is not None


@pytest.mark.unit
def test_find_leak_clean():
    messages = [{"role": "user", "content": "How many singers are there?"}]
    assert find_leak(messages, "SELECT count(*) FROM singer", [[4]]) is None


def _record(match, first_try, blocked=0, difficulty="easy", steps=None):
    return {
        "match": match,
        "first_try_valid": first_try,
        "blocked_count": blocked,
        "tool_calls": 2,
        "latency_ms": 1000,
        "tokens_in": 100,
        "tokens_out": 20,
        "difficulty": difficulty,
        "steps": steps or [{"tool": "run_query"}],
    }


@pytest.mark.unit
def test_compute_metrics():
    records = [
        _record(True, True, difficulty="easy"),
        _record(True, False, difficulty="hard"),  # recovered
        _record(False, False, blocked=1, difficulty="hard"),
    ]
    m = compute_metrics(records)
    assert m["questions"] == 3
    assert m["execution_accuracy"] == round(2 / 3, 4)
    assert m["first_try_valid_rate"] == round(1 / 3, 4)
    assert m["recovery_rate"] == round(1 / 2, 4)  # 2 failed first, 1 recovered
    assert m["accuracy_by_difficulty"]["easy"] == 1.0
    assert m["accuracy_by_difficulty"]["hard"] == 0.5
