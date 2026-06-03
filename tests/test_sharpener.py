"""HypothesisSharpener — Stage 2 수렴 (메커니즘 명시 + 최종 HypothesisOutput)."""
from unittest.mock import patch, call

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


def _hypothesis_round2(raw_idea=""):
    """DeepCritique 2라운드 후 강화된 가설."""
    return HypothesisOutput(
        raw_idea=raw_idea,
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        mechanism_path="버튼 상단 이동 → 시야 진입 → 클릭 → 전환",
        confounder_candidates=["요일 효과", "모바일 vs 데스크탑 환경 차이"],
        measurability_confirmed=True,
        sharpened_hypothesis="모바일 사용자 대상으로 결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
        causal_alternative=None,
        rejected_alternatives=[
            RejectedAlternative(hypothesis="게스트 결제", rejection_reason="범위 과다"),
            RejectedAlternative(
                hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
                rejection_reason="데스크탑 환경에서는 반례 존재: 버튼이 이미 시야 내에 있어 효과 없음",
            ),
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


# ── DeepCritique 2라운드 테스트 ──────────────────────────────────────────────

def test_quick_mode_calls_llm_once():
    """Quick 모드: call_structured 1회만 호출."""
    with patch("src.hypothesis.sharpener.call_structured", return_value=_hypothesis()) as mock_cs:
        out = sharpen(
            "결제 전환율을 올리고 싶다",
            _expander(),
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
            mode="quick",
        )
    assert mock_cs.call_count == 1
    assert isinstance(out, HypothesisOutput)


def test_deep_mode_calls_llm_twice():
    """Deep 모드: call_structured 2회 호출 (1라운드 수렴 + 2라운드 DeepCritique)."""
    round1 = _hypothesis()
    round2 = _hypothesis_round2()
    with patch("src.hypothesis.sharpener.call_structured", side_effect=[round1, round2]) as mock_cs:
        out = sharpen(
            "결제 전환율을 올리고 싶다",
            _expander(),
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
            mode="deep",
        )
    assert mock_cs.call_count == 2
    assert isinstance(out, HypothesisOutput)


def test_deep_mode_result_is_round2_output():
    """Deep 모드: 최종 결과는 2라운드 DeepCritique 결과여야 함."""
    round1 = _hypothesis()
    round2 = _hypothesis_round2()
    with patch("src.hypothesis.sharpener.call_structured", side_effect=[round1, round2]):
        out = sharpen(
            "결제 전환율을 올리고 싶다",
            _expander(),
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
            mode="deep",
        )
    assert out.sharpened_hypothesis == round2.sharpened_hypothesis
    assert "모바일" in out.sharpened_hypothesis


def test_deep_mode_raw_idea_forced_from_input():
    """Deep 모드: 2라운드 결과도 raw_idea가 입력값으로 강제 세팅됨."""
    round1 = _hypothesis(raw_idea="")
    round2 = _hypothesis_round2(raw_idea="")
    with patch("src.hypothesis.sharpener.call_structured", side_effect=[round1, round2]):
        out = sharpen(
            "결제 전환율을 올리고 싶다",
            _expander(),
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
            mode="deep",
        )
    assert out.raw_idea == "결제 전환율을 올리고 싶다"


def test_deep_mode_second_call_uses_round1_hypothesis():
    """Deep 모드 2라운드: 1라운드 sharpened_hypothesis가 2라운드 프롬프트에 포함됨."""
    round1 = _hypothesis()
    round2 = _hypothesis_round2()
    with patch("src.hypothesis.sharpener.call_structured", side_effect=[round1, round2]) as mock_cs:
        sharpen(
            "결제 전환율을 올리고 싶다",
            _expander(),
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
            mode="deep",
        )
    # 2라운드 호출 시 prompt에 1라운드 sharpened_hypothesis가 포함돼야 함
    second_call_kwargs = mock_cs.call_args_list[1]
    prompt_arg = second_call_kwargs.kwargs.get("prompt") or second_call_kwargs.args[0]
    assert round1.sharpened_hypothesis in prompt_arg


def test_deep_mode_confounder_can_be_enriched():
    """Deep 모드: 2라운드에서 confounder_candidates가 더 풍부해질 수 있음."""
    round1 = _hypothesis()
    round2 = _hypothesis_round2()
    assert len(round2.confounder_candidates) >= len(round1.confounder_candidates)
    with patch("src.hypothesis.sharpener.call_structured", side_effect=[round1, round2]):
        out = sharpen(
            "결제 전환율을 올리고 싶다",
            _expander(),
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
            mode="deep",
        )
    assert len(out.confounder_candidates) >= len(round1.confounder_candidates)
