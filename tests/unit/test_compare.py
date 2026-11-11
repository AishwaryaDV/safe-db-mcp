import pytest
from eval.compare import format_table


@pytest.mark.unit
def test_format_table():
    metas = [
        {
            "experiment": "baseline",
            "split": "tune",
            "model": "sonnet",
            "metrics": {
                "execution_accuracy": 0.42,
                "first_try_valid_rate": 0.92,
                "recovery_rate": 0.5,
                "blocked_query_rate": 0.0,
                "scored": 26,
            },
        },
        {
            "experiment": "no_hints",
            "split": "tune",
            "model": "sonnet",
            "metrics": {
                "execution_accuracy": 0.38,
                "first_try_valid_rate": 0.9,
                "recovery_rate": 0.3,
                "blocked_query_rate": 0.0,
                "scored": 26,
            },
        },
    ]
    table = format_table(metas)
    assert "| experiment | split | model" in table
    assert "baseline" in table and "no_hints" in table
    assert "0.42" in table and "0.38" in table
