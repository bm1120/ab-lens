"""TrivialRouter — A/B 테스트 대상이 아닌 사소한 변경 걸러내기."""
from unittest.mock import patch

from src.hypothesis.trivial_router import TrivialVerdict, route_trivial
from src.schemas import LLMProvider


def _route(idea):
    return route_trivial(idea, api_key="k", provider=LLMProvider.ANTHROPIC)


def test_trivial_input_flagged():
    verdict = TrivialVerdict(is_trivial=True, reason="오타 수정은 A/B 대상이 아님 — Just Do It")
    with patch("src.hypothesis.trivial_router.call_structured", return_value=verdict):
        out = _route("버튼 라벨 오타 수정")
    assert out.is_trivial is True
    assert "Just Do It" in out.reason


def test_substantive_idea_not_flagged():
    verdict = TrivialVerdict(is_trivial=False, reason="전환율에 영향을 줄 수 있는 변경")
    with patch("src.hypothesis.trivial_router.call_structured", return_value=verdict):
        out = _route("결제 버튼을 상단으로 이동")
    assert out.is_trivial is False


def test_route_trivial_passes_schema_to_call_structured():
    verdict = TrivialVerdict(is_trivial=False, reason="x")
    with patch("src.hypothesis.trivial_router.call_structured", return_value=verdict) as m:
        _route("아무 아이디어")
    # call_structured 가 TrivialVerdict 스키마로 호출됐는지
    assert m.call_args.kwargs["schema"] is TrivialVerdict
