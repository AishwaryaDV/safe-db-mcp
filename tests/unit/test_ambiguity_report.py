import pytest
from eval.ambiguity_report import tally


@pytest.mark.unit
def test_tally_counts_scores():
    rows = [
        {"score": "good"},
        {"score": "Bad"},
        {"score": "good"},
        {"score": ""},  # unscored, ignored
        {"score": "  good "},
    ]
    assert tally(rows) == {"good": 3, "bad": 1}


@pytest.mark.unit
def test_tally_empty():
    assert tally([{"score": ""}, {"score": "  "}]) == {}
