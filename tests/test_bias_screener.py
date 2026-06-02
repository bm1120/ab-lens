"""BiasScreener — 설계 시점 편향 스크리닝 (Quick 3종 / Deep 7종, Warning only)."""
from unittest.mock import patch

from src.hypothesis.bias_screener import QUICK_BIASES, screen_bias
from src.design_schemas import BiasScreenItem, BiasScreenResult
from src.schemas import LLMProvider


def _item(bias_type, status="active"):
    return BiasScreenItem(
        bias_type=bias_type, status=status, evidence="e", counter_measure="c"
    )


def _result(items, active_count=999):
    # active_count 를 일부러 틀리게 줘서 재계산되는지 확인
    return BiasScreenResult(biases=items, active_count=active_count)


def _screen(mode, items):
    with patch("src.hypothesis.bias_screener.call_structured", return_value=_result(items)):
        return screen_bias("결제 버튼 상단 이동 가설", mode=mode, api_key="k", provider=LLMProvider.ANTHROPIC)


def test_quick_keeps_only_three_biases():
    seven = [
        _item("confirmation_bias"), _item("anchoring"), _item("sunk_cost_fallacy"),
        _item("p_hacking"), _item("novelty_effect"), _item("survivorship_bias"),
        _item("causal_illusion"),
    ]
    out = _screen("quick", seven)
    assert {b.bias_type for b in out.biases} == set(QUICK_BIASES)


def test_deep_keeps_all():
    seven = [
        _item("confirmation_bias"), _item("anchoring"), _item("sunk_cost_fallacy"),
        _item("p_hacking"), _item("novelty_effect"), _item("survivorship_bias"),
        _item("causal_illusion"),
    ]
    out = _screen("deep", seven)
    assert len(out.biases) == 7


def test_active_count_recomputed():
    items = [_item("confirmation_bias", "active"), _item("anchoring", "latent"), _item("sunk_cost_fallacy", "active")]
    out = _screen("quick", items)
    assert out.active_count == 2  # 999 가 아니라 실제 active 수


def test_warning_only_true():
    out = _screen("quick", [_item("confirmation_bias")])
    assert out.warning_only is True
