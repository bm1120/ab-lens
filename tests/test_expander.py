"""HypothesisExpander — Stage 1 발산 (JTBD 재프레이밍 + 대안 가설)."""
from unittest.mock import patch

from src.hypothesis.expander import ExpanderOutput, expand
from src.schemas import LLMProvider


def test_expand_returns_candidates():
    fake = ExpanderOutput(
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        candidate_hypotheses=[
            "결제 버튼을 상단으로 옮긴다",
            "결제 단계를 1단계로 줄인다",
            "게스트 결제를 추가한다",
        ],
    )
    with patch("src.hypothesis.expander.call_structured", return_value=fake) as m:
        out = expand("결제 전환율을 올리고 싶다", api_key="k", provider=LLMProvider.ANTHROPIC)
    assert len(out.candidate_hypotheses) == 3
    assert m.call_args.kwargs["schema"] is ExpanderOutput
