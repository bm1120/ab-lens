"""설계 품질 룰브릭 (필수/권고 분리, 강제 차단 없음).

REQUIRED_ITEMS 는 통과 여부만(metric/randomization 명확). ADVISORY_ITEMS 는
가중치 점수(합 100). advisory_score 가 낮아도 차단하지 않고 강한 경고만 한다.
"""
from typing import Literal

REQUIRED_ITEMS: dict[str, str] = {
    "primary_metric_defined": "primary 지표 명확",
    "randomization_unit_clear": "실험 단위 명시",
}

ADVISORY_ITEMS: dict[str, int] = {
    "hypothesis_sharpened": 20,
    "mechanism_path_clear": 15,
    "mde_business_meaningful": 15,
    "sufficient_sample_size": 20,
    "stop_criteria_agreed": 15,
    "srm_prevention_checked": 10,
    "secondary_metrics_bounded": 5,
}


def score_advisory(passed: dict[str, bool]) -> int:
    """통과한 권고 항목의 가중치 합. 알 수 없는 키는 무시."""
    return sum(w for k, w in ADVISORY_ITEMS.items() if passed.get(k))


def grade(advisory_score: int) -> Literal["go", "advisory", "strong_warning"]:
    if advisory_score >= 70:
        return "go"
    if advisory_score >= 50:
        return "advisory"
    return "strong_warning"
