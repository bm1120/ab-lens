"""골든셋 회귀 판정 로직(evaluate) — 결정론, mock 불필요(평소 테스트에 포함)."""
from tests.golden.runner import evaluate


def test_all_pass():
    res = evaluate([True, True, True, True, True], threshold=4)
    assert res.passed is True
    assert res.hits == 5


def test_exactly_threshold_passes():
    res = evaluate([True, True, True, True, False], threshold=4)
    assert res.passed is True
    assert res.hits == 4


def test_below_threshold_fails():
    res = evaluate([True, True, True, False, False], threshold=4)
    assert res.passed is False
    assert res.hits == 3


def test_empty_fails():
    res = evaluate([], threshold=4)
    assert res.passed is False
    assert res.hits == 0


def test_total_reflects_runs():
    res = evaluate([True, False, True], threshold=2)
    assert res.total == 3
    assert res.hits == 2
    assert res.passed is True
