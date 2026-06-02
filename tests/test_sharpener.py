"""HypothesisSharpener — Stage 2 수렴 (메커니즘 명시 + 최종 HypothesisOutput)."""
from unittest.mock import patch

from src.hypothesis.expander import ExpanderOutput
from src.hypothesis.sharpener import sharpen
from src.design_schemas import HypothesisOutput, RejectedAlternative
from src.schemas import LLMProvider


def _expander():
    return ExpanderOutput(
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        candidate_hypotheses=["버튼 상단 이동", "단계 축소", "게스트 결제"],
    )


def _hypothesis(raw_idea=""):
    return HypothesisOutput(
        raw_idea=raw_idea,
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        mechanism_path="버튼 상단 이동 → 시야 진입 → 클릭 → 전환",
        confounder_candidates=["요일 효과"],
        measurability_confirmed=True,
        sharpened_hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
        causal_alternative=None,
        rejected_alternatives=[
            RejectedAlternative(hypothesis="게스트 결제", rejection_reason="범위 과다")
        ],
    )


def test_sharpen_returns_hypothesis_output():
    with patch("src.hypothesis.sharpener.call_structured", return_value=_hypothesis()):
        out = sharpen("결제 전환율을 올리고 싶다", _expander(), api_key="k", provider=LLMProvider.ANTHROPIC)
    assert isinstance(out, HypothesisOutput)
    assert out.rejected_alternatives  # 기각 대안 Decision Log


def test_sharpen_forces_raw_idea_from_input():
    # LLM 이 raw_idea 를 비워도 입력 아이디어로 강제 세팅
    with patch("src.hypothesis.sharpener.call_structured", return_value=_hypothesis(raw_idea="")):
        out = sharpen("결제 전환율을 올리고 싶다", _expander(), api_key="k", provider=LLMProvider.ANTHROPIC)
    assert out.raw_idea == "결제 전환율을 올리고 싶다"
