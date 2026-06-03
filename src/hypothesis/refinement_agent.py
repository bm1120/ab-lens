"""RefinementAgent — 소크라테스식 질문으로 약한 축을 개선.

두 기능:
1. generate_targeted_questions: 약한 축을 공격하는 1-2개의 타깃 질문 생성
2. refine_with_answer: 사용자 답변으로 가설의 관련 필드만 업데이트

약한 축별 질문 전략:
- clarity: 가설의 명확성/구체성 확인
- mechanism: 인과 경로(개입→행동→지표) 확인
- measurability: 측정 방법/지표 확인
- bias_risk: 잠재적 편향/혼란변수 확인
"""
from __future__ import annotations

from src.design_schemas import HypothesisOutput, ServiceContext
from src.llm_json import call_structured
from src.schemas import LLMProvider

SYSTEM_QUESTIONS_KO = (
    "당신은 A/B 테스트 가설 개선 전문가입니다. "
    "제공된 가설의 약한 축(weak_axes)을 개선하기 위해 "
    "사용자에게 1~2개의 소크라테스식 질문을 생성하세요. "
    "질문은 해당 축의 핵심 문제를 정확하게 공략해야 합니다:\n"
    "- clarity 약점: 가설 문장의 모호함, 범위 불명확 공략\n"
    "- mechanism 약점: 개입→행동 변화→지표의 인과 경로 공략\n"
    "- measurability 약점: 실제 측정 방법, 데이터 수집 가능성 공략\n"
    "- bias_risk 약점: 혼란변수, 선택 편향, 측정 편향 공략\n"
    "질문 문자열의 JSON 배열만 반환하세요. 설명이나 다른 텍스트는 포함하지 마세요."
)

SYSTEM_QUESTIONS_EN = (
    "You are an A/B test hypothesis improvement expert. "
    "Generate 1-2 targeted Socratic questions to improve the weak axes of the provided hypothesis. "
    "Questions must precisely attack the core issue of each axis:\n"
    "- clarity weakness: target ambiguity and unclear scope in the hypothesis statement\n"
    "- mechanism weakness: target the causal chain (intervention→behavior change→metric)\n"
    "- measurability weakness: target actual measurement methods and data collection feasibility\n"
    "- bias_risk weakness: target confounders, selection bias, measurement bias\n"
    "Return ONLY a JSON array of question strings."
)

SYSTEM_REFINE_KO = (
    "당신은 A/B 테스트 가설 정련 전문가입니다. "
    "사용자 답변을 바탕으로 가설의 특정 축(axis)과 관련된 필드만 업데이트하세요. "
    "다른 필드는 원본 그대로 유지하세요. "
    "업데이트할 축과 관련 필드:\n"
    "- clarity: sharpened_hypothesis, jtbd_reframe\n"
    "- mechanism: mechanism_path, sharpened_hypothesis\n"
    "- measurability: measurability_confirmed, suggested_primary_metric, suggested_secondary_metrics\n"
    "- bias_risk: confounder_candidates, implicit_assumptions\n"
    "raw_idea는 절대 변경하지 마세요. "
    "반드시 HypothesisOutput JSON 스키마로만 답하세요."
)

SYSTEM_REFINE_EN = (
    "You are an A/B test hypothesis refiner. "
    "Based on the user's answer, update ONLY the fields related to the specified axis. "
    "Keep all other fields exactly as they are in the original. "
    "Fields to update per axis:\n"
    "- clarity: sharpened_hypothesis, jtbd_reframe\n"
    "- mechanism: mechanism_path, sharpened_hypothesis\n"
    "- measurability: measurability_confirmed, suggested_primary_metric, suggested_secondary_metrics\n"
    "- bias_risk: confounder_candidates, implicit_assumptions\n"
    "NEVER change raw_idea. "
    "Answer ONLY as HypothesisOutput JSON schema."
)


def _build_context_block(service_context: ServiceContext, lang: str) -> str:
    """ServiceContext를 프롬프트에 주입할 텍스트 블록으로 변환한다."""
    if lang == "ko":
        return (
            "\n\n[서비스 컨텍스트]\n"
            f"서비스명: {service_context.service_name}\n"
            f"타깃 사용자: {service_context.target_users}\n"
            f"주요 지표: {service_context.primary_metric}\n"
            f"현재 베이스라인: {service_context.current_baseline}\n"
            f"과거 실험: {service_context.past_experiments}\n"
            f"도메인 제약: {service_context.domain_constraints}"
        )
    return (
        "\n\n[Service Context]\n"
        f"Service Name: {service_context.service_name}\n"
        f"Target Users: {service_context.target_users}\n"
        f"Primary Metric: {service_context.primary_metric}\n"
        f"Current Baseline: {service_context.current_baseline}\n"
        f"Past Experiments: {service_context.past_experiments}\n"
        f"Domain Constraints: {service_context.domain_constraints}"
    )


def _build_hypothesis_summary(hypothesis: HypothesisOutput, lang: str) -> str:
    """가설 요약 텍스트 블록을 생성한다."""
    if lang == "ko":
        return (
            f"[현재 가설]\n"
            f"원 아이디어: {hypothesis.raw_idea}\n"
            f"정제된 가설: {hypothesis.sharpened_hypothesis}\n"
            f"JTBD: {hypothesis.jtbd_reframe}\n"
            f"메커니즘 경로: {hypothesis.mechanism_path}\n"
            f"측정 가능 여부: {hypothesis.measurability_confirmed}\n"
            f"주요 지표: {hypothesis.suggested_primary_metric}\n"
            f"혼란변수 후보: {', '.join(hypothesis.confounder_candidates)}\n"
            f"암묵적 전제: {', '.join(hypothesis.implicit_assumptions)}"
        )
    return (
        f"[Current Hypothesis]\n"
        f"Raw Idea: {hypothesis.raw_idea}\n"
        f"Sharpened Hypothesis: {hypothesis.sharpened_hypothesis}\n"
        f"JTBD: {hypothesis.jtbd_reframe}\n"
        f"Mechanism Path: {hypothesis.mechanism_path}\n"
        f"Measurability Confirmed: {hypothesis.measurability_confirmed}\n"
        f"Primary Metric: {hypothesis.suggested_primary_metric}\n"
        f"Confounder Candidates: {', '.join(hypothesis.confounder_candidates)}\n"
        f"Implicit Assumptions: {', '.join(hypothesis.implicit_assumptions)}"
    )


def generate_targeted_questions(
    weak_axes: list[str],
    hypothesis: HypothesisOutput,
    service_context: ServiceContext | None,
    lang: str = "ko",
    api_key: str = "",
    provider: LLMProvider = LLMProvider.ANTHROPIC,
    model: str | None = None,
) -> list[str]:
    """약한 축을 개선하기 위한 소크라테스식 타깃 질문 1~2개를 생성한다.

    Args:
        weak_axes: 개선이 필요한 약한 축 목록 (e.g. ['mechanism', 'clarity'])
        hypothesis: 현재 가설 출력
        service_context: 서비스 컨텍스트 (없으면 None)
        lang: 언어 코드 (ko/en)
        api_key: LLM API 키
        provider: LLM 제공자
        model: 사용할 모델명. None이면 provider별 기본값 사용.

    Returns:
        타깃 질문 문자열 리스트 (1~2개)
    """
    from src.llm_client import call_llm
    import re
    import json

    system = SYSTEM_QUESTIONS_KO if lang == "ko" else SYSTEM_QUESTIONS_EN

    hypothesis_block = _build_hypothesis_summary(hypothesis, lang)
    if service_context is not None:
        hypothesis_block += _build_context_block(service_context, lang)

    if lang == "ko":
        axes_str = ", ".join(weak_axes)
        prompt = (
            f"{hypothesis_block}\n\n"
            f"약한 축 (개선 필요): {axes_str}\n\n"
            f"위 약한 축을 공략하는 소크라테스식 질문 1~2개를 생성하세요."
        )
    else:
        axes_str = ", ".join(weak_axes)
        prompt = (
            f"{hypothesis_block}\n\n"
            f"Weak axes (need improvement): {axes_str}\n\n"
            f"Generate 1-2 Socratic questions targeting the above weak axes."
        )

    text = call_llm(prompt=prompt, system=system, api_key=api_key, provider=provider, lang=lang, model=model)

    # JSON 배열 추출
    code_block = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if code_block:
        return json.loads(code_block.group(1))
    bare = re.search(r"\[.*\]", text, re.DOTALL)
    if bare:
        return json.loads(bare.group(0))
    # 파싱 실패 시 텍스트 줄 단위로 분리
    lines = [line.strip().lstrip("-•*").strip() for line in text.strip().splitlines() if line.strip()]
    return lines[:2] if lines else [text.strip()[:200]]


def refine_with_answer(
    axis: str,
    user_answer: str,
    hypothesis: HypothesisOutput,
    service_context: ServiceContext | None,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> HypothesisOutput:
    """사용자 답변으로 가설의 특정 축 관련 필드만 업데이트한다.

    Args:
        axis: 개선할 축 이름 ('clarity', 'mechanism', 'measurability', 'bias_risk')
        user_answer: 해당 축에 대한 사용자의 답변
        hypothesis: 현재 가설 출력
        service_context: 서비스 컨텍스트 (없으면 None)
        api_key: LLM API 키
        provider: LLM 제공자
        lang: 언어 코드 (ko/en)
        model: 사용할 모델명. None이면 provider별 기본값 사용.

    Returns:
        업데이트된 HypothesisOutput
    """
    system = SYSTEM_REFINE_KO if lang == "ko" else SYSTEM_REFINE_EN
    if service_context is not None:
        system = system + _build_context_block(service_context, lang)

    hypothesis_block = _build_hypothesis_summary(hypothesis, lang)

    if lang == "ko":
        prompt = (
            f"{hypothesis_block}\n\n"
            f"개선 대상 축: {axis}\n"
            f"사용자 답변: {user_answer}\n\n"
            f"위 답변을 바탕으로 '{axis}' 축 관련 필드만 업데이트하여 "
            f"개선된 HypothesisOutput을 반환하세요. "
            f"나머지 필드는 원본 그대로 유지하세요."
        )
    else:
        prompt = (
            f"{hypothesis_block}\n\n"
            f"Axis to improve: {axis}\n"
            f"User answer: {user_answer}\n\n"
            f"Based on the above answer, update ONLY the '{axis}' axis-related fields "
            f"and return the improved HypothesisOutput. "
            f"Keep all other fields exactly as in the original."
        )

    updated = call_structured(
        prompt=prompt,
        system=system,
        schema=HypothesisOutput,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )

    # raw_idea는 절대 변경하지 않음 (강제)
    return updated.model_copy(update={"raw_idea": hypothesis.raw_idea})
