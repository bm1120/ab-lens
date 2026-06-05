"""
통계 분석 에이전트 테스트
- anthropic API 호출 없이 순수 통계 함수만 테스트
"""

import json
import math
import pytest
from pathlib import Path

from src.schemas import ABTestInput
from src.agents.statistical import analyze_stats

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def load_scenario(name: str) -> ABTestInput:
    """시나리오 JSON 파일을 로드합니다."""
    with open(SCENARIOS_DIR / f"{name}.json", encoding="utf-8") as f:
        data = json.load(f)
    return ABTestInput(**data)


class TestClearWin:
    """명확한 승리 시나리오 테스트"""

    def test_clear_win_significance(self):
        """p=0.02, 큰 효과크기 → 통계적으로 유의해야 함"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        assert result.is_significant is True, f"명확한 승리 시나리오는 유의해야 합니다. p={ab_input.p_value}"

    def test_clear_win_effect_size(self):
        """Treatment 0.15 - Control 0.10 = +5pp 효과크기"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        expected_pp = (0.15 - 0.10) * 100  # 5pp
        assert abs(result.effect_size_pp - expected_pp) < 0.01, (
            f"효과 크기 불일치: 기대={expected_pp}, 실제={result.effect_size_pp}"
        )

    def test_clear_win_relative_effect(self):
        """상대적 효과 크기: (0.15-0.10)/0.10 = 50%"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        expected_relative = ((0.15 - 0.10) / 0.10) * 100  # 50%
        assert abs(result.effect_size_relative_pct - expected_relative) < 0.1


class TestClearLoss:
    """명확한 손실 시나리오 테스트"""

    def test_clear_loss_significance(self):
        """p=0.01 → 통계적으로 유의해야 함"""
        ab_input = load_scenario("clear_loss")
        result = analyze_stats(ab_input)

        assert result.is_significant is True

    def test_clear_loss_negative_effect(self):
        """Treatment 0.06 - Control 0.10 = -4pp (음수여야 함)"""
        ab_input = load_scenario("clear_loss")
        result = analyze_stats(ab_input)

        assert result.effect_size_pp < 0, "손실 시나리오 효과 크기는 음수여야 합니다"
        expected_pp = (0.06 - 0.10) * 100  # -4pp
        assert abs(result.effect_size_pp - expected_pp) < 0.01


class TestSRMDetection:
    """SRM (Sample Ratio Mismatch) 감지 테스트"""

    def test_srm_detection(self):
        """샘플 비율 불균형 (9500:5500) → SRM 감지되어야 함"""
        ab_input = load_scenario("srm_detected")
        result = analyze_stats(ab_input)

        assert result.srm_detected is True, (
            f"SRM이 감지되어야 합니다. "
            f"샘플 비율: {ab_input.sample_size_treatment}:{ab_input.sample_size_control}"
        )
        assert result.srm_detail is not None, "SRM 상세 정보가 있어야 합니다"

    def test_srm_not_detected_balanced(self):
        """균형 잡힌 샘플 (10000:10000) → SRM 감지되지 않아야 함"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        assert result.srm_detected is False, "균형 잡힌 샘플에서는 SRM이 감지되지 않아야 합니다"


class TestPowerCalculation:
    """검정력 분석 테스트"""

    def test_power_calculation(self):
        """검정력 계산이 0~100% 범위 내에 있어야 함"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        assert 0 <= result.power_pct <= 100, f"검정력이 범위를 벗어났습니다: {result.power_pct}"

    def test_low_power_needs_more_samples(self):
        """검정력이 낮으면 추가 샘플 수가 계산되어야 함"""
        ab_input = load_scenario("inconclusive")
        result = analyze_stats(ab_input)

        if result.power_pct < 80:
            assert result.additional_sample_needed is not None, (
                f"검정력 {result.power_pct:.1f}%로 낮으면 추가 샘플 수가 계산되어야 합니다"
            )
            assert result.additional_sample_needed > 0

    def test_high_power_scenario(self):
        """큰 샘플과 큰 효과크기 → 검정력이 높아야 함"""
        ab_input = load_scenario("clear_win")  # n=10000, effect=5pp
        result = analyze_stats(ab_input)

        assert result.power_pct > 90, (
            f"큰 샘플(n=10000)과 큰 효과(5pp)에서는 검정력이 90% 이상이어야 합니다. "
            f"실제: {result.power_pct:.1f}%"
        )


class TestEffectSizeCalculation:
    """효과 크기 계산 테스트"""

    def test_effect_size_calculation(self):
        """효과 크기가 정확히 계산되는지 검증"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        # pp 효과 크기
        expected_pp = (ab_input.treatment_value - ab_input.control_value) * 100
        assert abs(result.effect_size_pp - expected_pp) < 0.001

        # 상대 효과 크기
        expected_relative = ((ab_input.treatment_value - ab_input.control_value) / ab_input.control_value) * 100
        assert abs(result.effect_size_relative_pct - expected_relative) < 0.1

    def test_zero_control_value_handling(self):
        """Control 값이 0에 가까운 경우 처리"""
        ab_input = ABTestInput(
            metric_name="테스트 메트릭",
            treatment_value=0.05,
            control_value=0.001,
            p_value=0.03,
            sample_size_treatment=5000,
            sample_size_control=5000,
            experiment_days=7,
        )
        result = analyze_stats(ab_input)

        # 오류 없이 실행되어야 함
        assert result is not None
        assert result.effect_size_pp == pytest.approx(4.9, abs=0.01)

    def test_interpretation_contains_key_stats(self):
        """interpretation 필드에 주요 통계 수치가 포함되어야 함"""
        ab_input = load_scenario("clear_win")
        result = analyze_stats(ab_input)

        assert "effect_size_pp" in result.interpretation
        assert "p_value" in result.interpretation
        assert "power" in result.interpretation
        assert "srm" in result.interpretation


class TestConfidenceInterval:
    """효과크기 95% 신뢰구간 (효과크기 중심 보고)"""

    def test_clear_win_ci_excludes_zero(self):
        """명확한 승리(+5pp, n=10000) → CI가 0을 배제하고 하한>0"""
        result = analyze_stats(load_scenario("clear_win"))
        assert result.ci_includes_zero is False
        assert result.ci_low_pp > 0
        # 점추정(5pp)이 CI 안에 있어야
        assert result.ci_low_pp <= result.effect_size_pp <= result.ci_high_pp

    def test_ci_low_le_high(self):
        """CI 하한 ≤ 상한 (모든 시나리오 불변식)"""
        for name in ("clear_win", "clear_loss", "inconclusive"):
            r = analyze_stats(load_scenario(name))
            assert r.ci_low_pp <= r.ci_high_pp

    def test_ci_includes_zero_flag_consistent(self):
        """ci_includes_zero 플래그가 경계와 일관"""
        r = analyze_stats(load_scenario("inconclusive"))
        assert r.ci_includes_zero == (r.ci_low_pp <= 0.0 <= r.ci_high_pp)

    def test_interpretation_contains_ci(self):
        """interpretation raw 요약에 ci95 포함"""
        r = analyze_stats(load_scenario("clear_win"))
        assert "ci95_pp" in r.interpretation


class TestNoExperiment:
    """무작위 배정 없는 시나리오 테스트"""

    def test_non_random_assignment_analysis(self):
        """무작위 배정이 없어도 통계는 계산되어야 함"""
        ab_input = load_scenario("no_experiment")
        result = analyze_stats(ab_input)

        assert result is not None
        assert result.interpretation is not None
        # 무작위 배정 여부는 통계 분석에 직접 반영되지 않음 (LLM이 해석)
        assert ab_input.is_random_assignment is False
