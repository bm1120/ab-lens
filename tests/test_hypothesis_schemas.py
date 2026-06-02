"""탭1 가설 고도화 출력 스키마 (HypothesisOutput, BiasScreen*)."""
import pytest
from pydantic import ValidationError

from src.design_schemas import (
    BiasScreenItem,
    BiasScreenResult,
    HypothesisOutput,
    RejectedAlternative,
)


def test_bias_screen_item_accepts_pool_value():
    item = BiasScreenItem(
        bias_type="confirmation_bias",
        status="active",
        evidence="선호 결과를 지지하는 지표만 보고 있음",
        counter_measure="사전 등록된 1차 지표로만 판단",
    )
    assert item.bias_type == "confirmation_bias"


def test_bias_screen_item_rejects_unknown_bias():
    with pytest.raises(ValidationError):
        BiasScreenItem(
            bias_type="made_up_bias",
            status="active",
            evidence="x",
            counter_measure="y",
        )


def test_bias_screen_result_defaults_warning_only():
    result = BiasScreenResult(biases=[], active_count=0)
    assert result.warning_only is True


def test_hypothesis_output_full():
    out = HypothesisOutput(
        raw_idea="클릭률을 올리고 싶다",
        jtbd_reframe="사용자가 핵심 행동을 더 쉽게 완료하도록",
        implicit_assumptions=["버튼 위치가 클릭률의 병목이다"],
        mechanism_path="버튼 상단 이동 → 시야 진입 → 클릭 증가",
        confounder_candidates=["요일 효과"],
        measurability_confirmed=True,
        sharpened_hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
        causal_alternative=None,
        rejected_alternatives=[
            RejectedAlternative(hypothesis="색만 바꾼다", rejection_reason="측정 불가")
        ],
    )
    assert out.experiment_feasible is True
    assert out.rejected_alternatives[0].rejection_reason == "측정 불가"
