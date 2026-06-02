"""설계 품질 룰브릭 — 필수/권고 분리, 강제 차단 없음."""
from src.design_rubric import (
    ADVISORY_ITEMS,
    REQUIRED_ITEMS,
    grade,
    score_advisory,
)


def test_advisory_weights_sum_to_100():
    assert sum(ADVISORY_ITEMS.values()) == 100


def test_required_items_present():
    assert "primary_metric_defined" in REQUIRED_ITEMS
    assert "randomization_unit_clear" in REQUIRED_ITEMS


def test_score_all_passed_is_100():
    passed = {k: True for k in ADVISORY_ITEMS}
    assert score_advisory(passed) == 100


def test_score_none_passed_is_0():
    passed = {k: False for k in ADVISORY_ITEMS}
    assert score_advisory(passed) == 0


def test_score_ignores_unknown_keys():
    assert score_advisory({"nonexistent": True}) == 0


def test_grade_thresholds():
    assert grade(85) == "go"
    assert grade(70) == "go"
    assert grade(60) == "advisory"
    assert grade(50) == "advisory"
    assert grade(40) == "strong_warning"
