"""tests/test_refinement_agent.py — RefinementAgent 단위 테스트.

실제 refinement_agent.py 인터페이스:
  generate_targeted_questions(weak_axes, hypothesis, service_context, lang, api_key, provider, model)
    → call_llm 을 직접 호출해 JSON 배열 파싱
  refine_with_answer(axis, user_answer, hypothesis, service_context, api_key, provider, lang, model)
    → call_structured 호출해 HypothesisOutput 반환
"""
import json
from unittest.mock import patch

from src.design_schemas import HypothesisOutput, RejectedAlternative, ServiceContext
from src.hypothesis.refinement_agent import generate_targeted_questions, refine_with_answer
from src.schemas import LLMProvider


# ── 공통 픽스처 ───────────────────────────────────────────────────────────────

def _hypothesis(mechanism_path: str = "버튼 이동 → 시야 진입 → 클릭 → 전환") -> HypothesisOutput:
    return HypothesisOutput(
        raw_idea="결제 전환율을 올리고 싶다",
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        mechanism_path=mechanism_path,
        confounder_candidates=["요일 효과"],
        measurability_confirmed=True,
        sharpened_hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
    )


def _refined_hypothesis(mechanism_path: str = "버튼 이동 → 시야 진입 → 클릭 → 전환 (개선됨)") -> HypothesisOutput:
    """refine_with_answer mock 에서 반환할 개선된 가설."""
    return HypothesisOutput(
        raw_idea="결제 전환율을 올리고 싶다",
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        mechanism_path=mechanism_path,
        confounder_candidates=["요일 효과", "디바이스 타입"],
        measurability_confirmed=True,
        sharpened_hypothesis="모바일 사용자 대상으로 결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
    )


# ── Task G3: Test 1 — generate_targeted_questions returns 1-2 questions ──────

def test_generate_targeted_questions_length():
    """generate_targeted_questions 가 1~2개 질문을 반환해야 한다."""
    hyp = _hypothesis()
    fake_llm_response = json.dumps(["메커니즘 경로를 더 구체적으로 설명해 주세요.", "어떤 행동 변화를 기대하시나요?"])

    with patch("src.llm_client.call_llm", return_value=fake_llm_response):
        result = generate_targeted_questions(
            weak_axes=["mechanism"],
            hypothesis=hyp,
            service_context=None,
            lang="ko",
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert isinstance(result, list)
    assert 1 <= len(result) <= 2


def test_generate_targeted_questions_returns_strings():
    """반환 리스트의 모든 요소가 문자열이어야 한다."""
    hyp = _hypothesis()
    fake_llm_response = '["측정 방법을 명확히 해 주세요."]'

    with patch("src.llm_client.call_llm", return_value=fake_llm_response):
        result = generate_targeted_questions(
            weak_axes=["measurability"],
            hypothesis=hyp,
            service_context=None,
            lang="ko",
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert all(isinstance(q, str) for q in result)


def test_generate_targeted_questions_with_multiple_weak_axes():
    """여러 약점 축이 있어도 LLM 응답대로 질문을 반환한다.

    시스템 프롬프트에 1~2개 요청하므로 보통 1~2개가 반환되나,
    구현이 추가로 자르지는 않는다.
    """
    hyp = _hypothesis()
    # LLM 이 2개만 반환하는 정상 케이스
    fake_llm_response = json.dumps([
        "메커니즘을 더 구체적으로?",
        "측정 방법은?",
    ])

    with patch("src.llm_client.call_llm", return_value=fake_llm_response):
        result = generate_targeted_questions(
            weak_axes=["mechanism", "measurability", "clarity"],
            hypothesis=hyp,
            service_context=None,
            lang="ko",
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert isinstance(result, list)
    assert len(result) >= 1


def test_generate_targeted_questions_calls_llm():
    """generate_targeted_questions 가 call_llm 을 1회 호출한다."""
    hyp = _hypothesis()
    fake_llm_response = '["질문1"]'

    with patch("src.llm_client.call_llm", return_value=fake_llm_response) as mock_llm:
        generate_targeted_questions(
            weak_axes=["clarity"],
            hypothesis=hyp,
            service_context=None,
            lang="ko",
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert mock_llm.call_count == 1


def test_generate_targeted_questions_prompt_contains_weak_axes():
    """프롬프트에 약점 축 정보가 포함돼야 한다."""
    hyp = _hypothesis()
    fake_llm_response = '["질문1"]'

    with patch("src.llm_client.call_llm", return_value=fake_llm_response) as mock_llm:
        generate_targeted_questions(
            weak_axes=["mechanism"],
            hypothesis=hyp,
            service_context=None,
            lang="ko",
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    prompt_arg = mock_llm.call_args.kwargs.get("prompt") or mock_llm.call_args.args[0]
    assert "mechanism" in prompt_arg


def test_generate_targeted_questions_with_service_context():
    """service_context 가 있으면 프롬프트에 컨텍스트 정보가 포함된다."""
    hyp = _hypothesis()
    ctx = ServiceContext(
        service_name="MyShop",
        target_users="모바일 사용자",
        primary_metric="checkout_conversion",
        current_baseline="10%",
        past_experiments="3회",
        domain_constraints="없음",
    )
    fake_llm_response = '["질문1"]'

    with patch("src.llm_client.call_llm", return_value=fake_llm_response) as mock_llm:
        generate_targeted_questions(
            weak_axes=["clarity"],
            hypothesis=hyp,
            service_context=ctx,
            lang="ko",
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    # 컨텍스트 내용이 prompt 또는 system 어딘가에 포함되어야 함
    prompt_arg = mock_llm.call_args.kwargs.get("prompt") or mock_llm.call_args.args[0]
    system_arg = mock_llm.call_args.kwargs.get("system") or ""
    assert "MyShop" in prompt_arg or "MyShop" in system_arg


# ── Task G3: Test 2 — refine_with_answer returns updated HypothesisOutput ────

def test_refine_with_answer_returns_hypothesis_output():
    """refine_with_answer 가 HypothesisOutput 인스턴스를 반환해야 한다."""
    hyp = _hypothesis()
    refined = _refined_hypothesis()

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined):
        result = refine_with_answer(
            axis="mechanism",
            user_answer="버튼을 화면 상단 30% 위치에 배치하면 시야에 즉각 들어옵니다.",
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert isinstance(result, HypothesisOutput)


def test_refine_with_answer_preserves_raw_idea():
    """refine_with_answer 는 raw_idea 를 원본 그대로 유지해야 한다."""
    hyp = _hypothesis()
    refined = _refined_hypothesis()
    # LLM 이 raw_idea 를 바꿔 버려도 원본으로 복원해야 함
    refined_with_changed_idea = refined.model_copy(update={"raw_idea": "LLM이 바꾼 아이디어"})

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined_with_changed_idea):
        result = refine_with_answer(
            axis="clarity",
            user_answer="더 구체적으로 모바일 대상으로 한정합니다.",
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert result.raw_idea == hyp.raw_idea


# ── Task G3: Test 3 — refine_with_answer for 'mechanism' axis updates mechanism_path ──

def test_refine_mechanism_axis():
    """axis='mechanism' 이면 mechanism_path 가 업데이트돼야 한다."""
    hyp = _hypothesis(mechanism_path="버튼 이동 → 클릭 → 전환")
    improved_path = "결제 버튼 상단 배치 → 시야 즉각 진입 → 클릭 확률 증가 → checkout_conversion 상승"
    refined = _refined_hypothesis(mechanism_path=improved_path)

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined):
        result = refine_with_answer(
            axis="mechanism",
            user_answer="버튼을 화면 상단 30% 위치에 배치하면 사용자 시야에 즉각 들어옵니다.",
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert result.mechanism_path == improved_path


def test_refine_with_answer_calls_call_structured():
    """refine_with_answer 가 call_structured 를 1회 호출한다."""
    hyp = _hypothesis()
    refined = _refined_hypothesis()

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined) as mock_cs:
        refine_with_answer(
            axis="measurability",
            user_answer="Mixpanel로 클릭 이벤트를 추적합니다.",
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    assert mock_cs.call_count == 1


def test_refine_with_answer_schema_is_hypothesis_output():
    """call_structured 에 HypothesisOutput 스키마가 전달돼야 한다."""
    hyp = _hypothesis()
    refined = _refined_hypothesis()

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined) as mock_cs:
        refine_with_answer(
            axis="bias_risk",
            user_answer="요일 효과를 통제하기 위해 2주 이상 실험합니다.",
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    schema_arg = mock_cs.call_args.kwargs.get("schema") or mock_cs.call_args.args[2]
    assert schema_arg is HypothesisOutput


def test_refine_with_answer_prompt_contains_axis():
    """프롬프트에 개선 대상 축이 포함돼야 한다."""
    hyp = _hypothesis()
    refined = _refined_hypothesis()

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined) as mock_cs:
        refine_with_answer(
            axis="clarity",
            user_answer="가설을 모바일 신규 사용자로 한정합니다.",
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    prompt_arg = mock_cs.call_args.kwargs.get("prompt") or mock_cs.call_args.args[0]
    assert "clarity" in prompt_arg


def test_refine_with_answer_prompt_contains_user_answer():
    """프롬프트에 사용자 답변이 포함돼야 한다."""
    hyp = _hypothesis()
    refined = _refined_hypothesis()
    user_answer = "Amplitude로 이벤트를 추적합니다."

    with patch("src.hypothesis.refinement_agent.call_structured", return_value=refined) as mock_cs:
        refine_with_answer(
            axis="measurability",
            user_answer=user_answer,
            hypothesis=hyp,
            service_context=None,
            api_key="k",
            provider=LLMProvider.ANTHROPIC,
        )

    prompt_arg = mock_cs.call_args.kwargs.get("prompt") or mock_cs.call_args.args[0]
    assert user_answer in prompt_arg
