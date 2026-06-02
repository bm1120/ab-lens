"""통계 분석 에이전트"""

import math
from scipy import stats
from scipy.stats import chi2_contingency
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

from src.schemas import ABTestInput, StatisticalResult


def analyze_stats(input: ABTestInput) -> StatisticalResult:
    """
    A/B 테스트 통계 분석을 수행합니다.
    - Two-proportion z-test
    - Statistical power analysis
    - Sample Ratio Mismatch (SRM) 감지
    """
    treatment = input.treatment_value
    control = input.control_value
    n_treatment = input.sample_size_treatment
    n_control = input.sample_size_control

    # 효과 크기 계산
    effect_size_pp = (treatment - control) * 100  # percentage points
    if control != 0:
        effect_size_relative_pct = ((treatment - control) / abs(control)) * 100
    else:
        effect_size_relative_pct = 0.0

    # 통계적 유의성 (p < 0.05)
    is_significant = input.p_value < 0.05

    # 검정력 분석
    # Cohen's h effect size for proportions
    try:
        h = proportion_effectsize(treatment, control)
        power_analysis = NormalIndPower()
        power = power_analysis.solve_power(
            effect_size=abs(h),
            nobs1=n_treatment,
            alpha=0.05,
            ratio=n_control / n_treatment if n_treatment > 0 else 1.0,
            alternative="two-sided",
        )
        power_pct = min(power * 100, 100.0)
    except Exception:
        power_pct = 0.0

    # 80% 검정력 달성에 필요한 샘플 수 계산
    additional_sample_needed: int | None = None
    try:
        if power_pct < 80.0 and abs(effect_size_pp) > 0:
            h = proportion_effectsize(treatment, control)
            power_analysis = NormalIndPower()
            required_n = power_analysis.solve_power(
                effect_size=abs(h),
                power=0.80,
                alpha=0.05,
                ratio=1.0,
                alternative="two-sided",
            )
            current_n = min(n_treatment, n_control)
            additional = max(0, math.ceil(required_n) - current_n)
            additional_sample_needed = additional * 2  # 양 그룹 합산
    except Exception:
        additional_sample_needed = None

    # SRM (Sample Ratio Mismatch) 감지
    # 기대 비율: 50:50 가정
    total = n_treatment + n_control
    expected_treatment = total * 0.5
    expected_control = total * 0.5

    srm_detected = False
    srm_detail: str | None = None

    try:
        observed = [n_treatment, n_control]
        expected = [expected_treatment, expected_control]
        chi2, p_srm = stats.chisquare(observed, f_exp=expected)

        if p_srm < 0.01:  # SRM 임계값: p < 0.01
            srm_detected = True
            actual_ratio = n_treatment / n_control if n_control > 0 else float("inf")
            srm_detail = (
                f"SRM 감지: Treatment/Control 비율 = {actual_ratio:.3f} "
                f"(기대값: 1.000), chi²={chi2:.2f}, p={p_srm:.4f}. "
                f"샘플 비율 불균형으로 인해 결과 신뢰성이 낮을 수 있습니다."
            )
    except Exception:
        pass

    # 통계 요약 (raw 수치)
    interpretation = (
        f"effect_size_pp={effect_size_pp:+.2f}pp, "
        f"effect_size_relative={effect_size_relative_pct:+.1f}%, "
        f"p_value={input.p_value:.4f}, "
        f"power={power_pct:.1f}%, "
        f"n_treatment={n_treatment}, n_control={n_control}, "
        f"srm={'yes' if srm_detected else 'no'}, "
        f"is_significant={'yes' if is_significant else 'no'}"
    )

    return StatisticalResult(
        effect_size_pp=effect_size_pp,
        effect_size_relative_pct=effect_size_relative_pct,
        is_significant=is_significant,
        power_pct=power_pct,
        srm_detected=srm_detected,
        srm_detail=srm_detail,
        additional_sample_needed=additional_sample_needed,
        interpretation=interpretation,
    )
