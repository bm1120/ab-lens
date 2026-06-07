"""추상 구성개념 분류 (clear / abstract / mixed). 불확실은 mixed로 보수 편향."""
from unittest.mock import patch

from src.hypothesis.classify import ConstructClassification, classify_construct
from src.schemas import LLMProvider


def _classify(ret):
    with patch("src.hypothesis.classify.call_structured", return_value=ret) as m:
        out = classify_construct("아이디어", api_key="k", provider=LLMProvider.CLAUDE_CODE)
    return out, m


def test_clear_passthrough():
    out, m = _classify(ConstructClassification(kind="clear", constructs=[], rationale="이미 측정가능"))
    assert out.kind == "clear"
    assert m.call_args.kwargs["schema"] is ConstructClassification


def test_abstract_with_constructs():
    out, _ = _classify(ConstructClassification(kind="abstract", constructs=["브랜드 인지도"], rationale="추상"))
    assert out.kind == "abstract"
    assert "브랜드 인지도" in out.constructs


def test_invalid_kind_coerced_to_mixed():
    # LLM이 잘못된 값/대문자/공백을 내도 mixed로 보수 편향 (거짓음성 방지)
    out = ConstructClassification.model_validate({"kind": "UNKNOWN", "constructs": [], "rationale": "x"})
    assert out.kind == "mixed"


def test_llm_failure_falls_back_to_mixed():
    with patch("src.hypothesis.classify.call_structured", side_effect=RuntimeError("api down")):
        out = classify_construct("아이디어", api_key="k", provider=LLMProvider.CLAUDE_CODE)
    assert out.kind == "mixed"  # 실패 시 측정확인 쪽으로 (안전)


def test_classify_uses_deterministic_temperature():
    with patch("src.hypothesis.classify.call_structured",
               return_value=ConstructClassification(kind="clear")) as m:
        classify_construct("아이디어", api_key="k", provider=LLMProvider.CLAUDE_CODE)
    assert m.call_args.kwargs.get("temperature") == 0.0  # 라우팅 결정 → 결정론
