"""ContextLoopGuard — v8 핵심 해자 (deterministic, LLM 아님).

탭1에서 약속한 DesignContext 와 탭2의 관측 결과를 대조해
통계적 양심을 강제한다: peeking / 지표 스왑(체리피킹) / MDE 미달.
"""
import pytest

from src.context_loop import ObservedResult, Violation, context_loop_guard
from tests.test_design_schemas import make_context


def observed(current_n=43000, significant_metric="checkout_conversion", effect=0.06):
    return ObservedResult(
        current_n=current_n,
        significant_metric=significant_metric,
        effect=effect,
    )


def kinds(violations):
    return {v.kind for v in violations}


def test_no_context_skips_check():
    # json 미업로드 → 대조 생략 (빈 리스트)
    assert context_loop_guard(None, observed()) == []


def test_clean_result_has_no_violations():
    ctx = make_context()  # target 43000, primary checkout_conversion, mde 0.05
    assert context_loop_guard(ctx, observed()) == []


def test_peeking_detected_when_sample_short():
    ctx = make_context()
    # 약속 43000의 60%만 도달
    result = context_loop_guard(ctx, observed(current_n=25800))
    assert "peeking" in kinds(result)
    peek = next(v for v in result if v.kind == "peeking")
    assert peek.severity == "high"
    assert "60%" in peek.message  # 도달률을 사람이 읽게 표기


def test_metric_swap_detected():
    ctx = make_context()
    # 유의하게 나온 지표가 약속한 1차 지표가 아님 (체리피킹)
    result = context_loop_guard(ctx, observed(significant_metric="signup_rate"))
    assert "metric_swap" in kinds(result)


def test_below_mde_is_warning_not_high():
    ctx = make_context()  # agreed_mde 0.05
    result = context_loop_guard(ctx, observed(effect=0.02))
    assert "below_mde" in kinds(result)
    below = next(v for v in result if v.kind == "below_mde")
    assert below.severity == "medium"


def test_multiple_violations_stack():
    ctx = make_context()
    result = context_loop_guard(
        ctx, observed(current_n=10000, significant_metric="signup_rate", effect=0.01)
    )
    assert kinds(result) == {"peeking", "metric_swap", "below_mde"}


def test_no_significant_metric_skips_swap_check():
    ctx = make_context()
    # 유의한 지표 없음(None) → 체리피킹 판정 대상 아님
    result = context_loop_guard(ctx, observed(significant_metric=None))
    assert "metric_swap" not in kinds(result)
