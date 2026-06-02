"""calculate_sample_size — 설계 시점 표본 크기 계산 (deterministic tool, 지표 3종)."""
import pytest

from src.design_stats import calculate_sample_size
from src.design_schemas import SamplePlanOutput


def test_proportion_known_benchmark():
    # baseline 10% → 15% (mde 5%p 절대), alpha 0.05, power 0.8
    # 분산기반 two-proportion z-test: group당 ~681명 (업계표준 계산기와 일치)
    out = calculate_sample_size(metric_type="proportion", baseline=0.10, mde=0.05)
    assert isinstance(out, SamplePlanOutput)
    assert 670 <= out.per_group <= 690
    assert out.total == out.per_group * 2


def test_smaller_mde_needs_more_samples():
    big = calculate_sample_size(metric_type="proportion", baseline=0.10, mde=0.05)
    small = calculate_sample_size(metric_type="proportion", baseline=0.10, mde=0.02)
    assert small.per_group > big.per_group


def test_continuous_requires_std_dev():
    with pytest.raises(ValueError, match="std_dev"):
        calculate_sample_size(metric_type="continuous", baseline=100.0, mde=5.0)


def test_continuous_with_std_dev():
    out = calculate_sample_size(
        metric_type="continuous", baseline=100.0, mde=5.0, std_dev=20.0
    )
    # effect size d = 5/20 = 0.25 → group당 약 250여 명
    assert out.per_group > 0
    assert out.total == out.per_group * 2


def test_count_metric_runs():
    out = calculate_sample_size(metric_type="count", baseline=2.0, mde=0.3)
    assert out.per_group > 0


def test_cluster_icc_inflates_sample():
    base = calculate_sample_size(metric_type="proportion", baseline=0.10, mde=0.05)
    clustered = calculate_sample_size(
        metric_type="proportion", baseline=0.10, mde=0.05, icc=0.05
    )
    # ICC > 0 → design effect 로 표본이 늘어야 한다
    assert clustered.total > base.total


def test_invalid_mde_rejected():
    with pytest.raises(ValueError):
        calculate_sample_size(metric_type="proportion", baseline=0.10, mde=0.0)
