"""
데모 시나리오 - 5개 합성 데이터 ABTestInput 객체
"""

from src.schemas import ABTestInput

# 시나리오 1: 명확한 승리 - 랜딩 페이지 최적화
CLEAR_WIN = ABTestInput(
    metric_name="전환율",
    treatment_value=0.15,
    control_value=0.10,
    p_value=0.02,
    sample_size_treatment=10000,
    sample_size_control=10000,
    experiment_days=21,
    dev_cost_weeks=2.0,
    business_priority="high",
    prior_expectation="신규 랜딩 페이지로 10% 이상 전환율 향상 기대",
    is_random_assignment=True,
    multiple_metrics=False,
    business_context="리브랜딩 캠페인의 일환으로 신규 랜딩 페이지를 테스트. 주요 KPI는 전환율이며 출시 여부를 결정해야 함.",
)

# 시나리오 2: 명확한 손실 - 체크아웃 플로우 변경
CLEAR_LOSS = ABTestInput(
    metric_name="구매 전환율",
    treatment_value=0.06,
    control_value=0.10,
    p_value=0.01,
    sample_size_treatment=8000,
    sample_size_control=8000,
    experiment_days=14,
    dev_cost_weeks=3.0,
    business_priority="high",
    prior_expectation="새로운 체크아웃 플로우로 전환율 개선 기대",
    is_random_assignment=True,
    multiple_metrics=False,
    business_context="결제 프로세스 간소화를 위해 3단계 체크아웃을 1단계로 줄이는 실험.",
)

# 시나리오 3: 결론 불분명 - 버튼 색상 변경
INCONCLUSIVE = ABTestInput(
    metric_name="클릭율 (CTR)",
    treatment_value=0.052,
    control_value=0.050,
    p_value=0.08,
    sample_size_treatment=6000,
    sample_size_control=6000,
    experiment_days=10,
    dev_cost_weeks=1.0,
    business_priority="medium",
    prior_expectation=None,
    is_random_assignment=True,
    multiple_metrics=False,
    business_context="버튼 색상을 파란색에서 주황색으로 변경하는 실험. 작은 개선이 보이지만 통계적으로 불분명.",
)

# 시나리오 4: SRM 감지 - 회원가입 폼
SRM_DETECTED = ABTestInput(
    metric_name="회원가입 전환율",
    treatment_value=0.13,
    control_value=0.12,
    p_value=0.04,
    sample_size_treatment=9500,
    sample_size_control=5500,
    experiment_days=14,
    dev_cost_weeks=2.0,
    business_priority="high",
    prior_expectation=None,
    is_random_assignment=True,
    multiple_metrics=False,
    business_context="신규 가입 폼 간소화 실험. 샘플 비율이 예상과 다르게 배분됨.",
)

# 시나리오 5: 무작위 배정 없음 - 지역별 가격 정책
NO_EXPERIMENT = ABTestInput(
    metric_name="매출 (ARPU)",
    treatment_value=0.18,
    control_value=0.15,
    p_value=0.06,
    sample_size_treatment=3000,
    sample_size_control=2800,
    experiment_days=30,
    dev_cost_weeks=None,
    business_priority="medium",
    prior_expectation=None,
    is_random_assignment=False,
    multiple_metrics=False,
    business_context="지역별로 서로 다른 가격 정책을 적용한 관찰 연구. 무작위 배정이 불가능하여 지역 단위로 비교함.",
)

# 전체 시나리오 목록
ALL_SCENARIOS = {
    "clear_win": CLEAR_WIN,
    "clear_loss": CLEAR_LOSS,
    "inconclusive": INCONCLUSIVE,
    "srm_detected": SRM_DETECTED,
    "no_experiment": NO_EXPERIMENT,
}


def get_scenario(name: str) -> ABTestInput:
    """시나리오 이름으로 ABTestInput 객체를 반환합니다."""
    if name not in ALL_SCENARIOS:
        raise ValueError(f"알 수 없는 시나리오: {name}. 가능한 옵션: {list(ALL_SCENARIOS.keys())}")
    return ALL_SCENARIOS[name]
