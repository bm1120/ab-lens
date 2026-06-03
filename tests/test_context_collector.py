"""tests/test_context_collector.py — ContextCollector 단위 테스트.

generate_context_questions, parse_answers_to_context 를 mock LLM 으로 검증.
"""
from unittest.mock import patch

from pydantic import BaseModel

from src.design_schemas import HypothesisOutput, RejectedAlternative, ServiceContext
from src.hypothesis.context_collector import (
    generate_context_questions,
    parse_answers_to_context,
)
from src.schemas import LLMProvider


# ── 공통 픽스처 ───────────────────────────────────────────────────────────────

def _hypothesis() -> HypothesisOutput:
    return HypothesisOutput(
        raw_idea="결제 전환율을 올리고 싶다",
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        mechanism_path="버튼 이동 → 시야 진입 → 클릭 → 전환",
        confounder_candidates=["요일 효과"],
        measurability_confirmed=True,
        sharpened_hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
    )


def _service_context() -> ServiceContext:
    return ServiceContext(
        service_name="MyShop",
        target_users="모바일 사용자",
        primary_metric="checkout_conversion",
        current_baseline="10%",
        past_experiments="3회 진행",
        domain_constraints="규제 없음",
    )


# ── Task G2: Test 1 — generate_context_questions returns list of strings ──────

def test_generate_questions_returns_list():
    """generate_context_questions 가 str 리스트를 반환해야 한다."""

    class QuestionList(BaseModel):
        questions: list[str]

    fake_result = QuestionList(
        questions=[
            "현재 결제 전환율 베이스라인은 얼마입니까?",
            "월간 활성 사용자 수는 어느 정도입니까?",
            "A/B 테스트 인프라가 구축돼 있습니까?",
        ]
    )

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_result):
        result = generate_context_questions(
            _hypothesis(), api_key="k", provider=LLMProvider.ANTHROPIC
        )

    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(isinstance(q, str) for q in result)


def test_generate_questions_calls_llm_once():
    """generate_context_questions 는 call_structured 를 정확히 1회 호출한다."""

    class QuestionList(BaseModel):
        questions: list[str]

    fake_result = QuestionList(questions=["질문1", "질문2"])

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_result) as mock_cs:
        generate_context_questions(
            _hypothesis(), api_key="k", provider=LLMProvider.ANTHROPIC
        )

    assert mock_cs.call_count == 1


def test_generate_questions_prompt_contains_hypothesis():
    """생성된 프롬프트에 가설의 핵심 내용이 포함돼야 한다."""

    class QuestionList(BaseModel):
        questions: list[str]

    fake_result = QuestionList(questions=["질문1"])
    hyp = _hypothesis()

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_result) as mock_cs:
        generate_context_questions(hyp, api_key="k", provider=LLMProvider.ANTHROPIC)

    prompt_arg = mock_cs.call_args.kwargs.get("prompt") or mock_cs.call_args.args[0]
    assert hyp.sharpened_hypothesis in prompt_arg


# ── Task G2: Test 2 — parse_answers_to_context returns ServiceContext ─────────

def test_parse_answers_returns_service_context():
    """parse_answers_to_context 가 올바른 ServiceContext 를 반환해야 한다."""
    questions = ["서비스 이름은?", "주요 사용자는?"]
    answers = ["MyShop", "모바일 사용자"]
    fake_ctx = _service_context()

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_ctx):
        result = parse_answers_to_context(
            questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
        )

    assert isinstance(result, ServiceContext)
    assert result.service_name == "MyShop"
    assert result.target_users == "모바일 사용자"


def test_parse_answers_context_fields_populated():
    """파싱 결과 ServiceContext 의 모든 필드가 채워져야 한다."""
    questions = ["Q1", "Q2"]
    answers = ["A1", "A2"]
    fake_ctx = _service_context()

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_ctx):
        result = parse_answers_to_context(
            questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
        )

    assert result.service_name
    assert result.primary_metric
    assert result.current_baseline
    assert result.past_experiments
    assert result.domain_constraints


def test_parse_answers_prompt_contains_qa_pairs():
    """프롬프트에 질문-답변 쌍이 포함돼야 한다."""
    questions = ["현재 전환율은?"]
    answers = ["10%"]
    fake_ctx = _service_context()

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_ctx) as mock_cs:
        parse_answers_to_context(
            questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
        )

    prompt_arg = mock_cs.call_args.kwargs.get("prompt") or mock_cs.call_args.args[0]
    assert "현재 전환율은?" in prompt_arg
    assert "10%" in prompt_arg


def test_parse_answers_schema_is_service_context():
    """call_structured 에 ServiceContext 스키마가 전달돼야 한다."""
    questions = ["Q1"]
    answers = ["A1"]
    fake_ctx = _service_context()

    with patch("src.hypothesis.context_collector.call_structured", return_value=fake_ctx) as mock_cs:
        parse_answers_to_context(
            questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
        )

    schema_arg = mock_cs.call_args.kwargs.get("schema") or mock_cs.call_args.args[2]
    assert schema_arg is ServiceContext
