"""HypothesisScorer — 가설 품질 점수 평가.

두 단계:
1. 결정론적 사전 필터 (mechanism_path 길이, measurability_confirmed)
2. LLM이 나머지 축 점수 + 종합 rationale 생성

점수 체계:
- clarity: 0-100 (가설의 명확성)
- mechanism: 0-100 (개입→행동→지표 인과 경로의 명확성)
- measurability: 0-100 (측정 가능성)
- bias_risk: 0-100 (높을수록 편향 위험 낮음, inverted)
- total: clarity*0.2 + mechanism*0.3 + measurability*0.3 + bias_risk*0.2
- passed: total >= 70
"""
from __future__ import annotations

from src.design_schemas import HypothesisOutput, QualityScore, ServiceContext
from src.llm_json import call_structured
from src.schemas import LLMProvider

SYSTEM_SCORE_KO = (
    "당신은 A/B 테스트 가설 품질 평가 전문가입니다. 제공된 가설을 다음 4개 축으로 점수를 매기세요 (0-100): "
    "1) clarity: 가설 문장이 얼마나 명확하고 구체적인가 "
    "2) mechanism: 개입→행동 변화→지표의 인과 경로가 얼마나 잘 설명되어 있는가 "
    "3) measurability: 주요 지표를 실제로 측정할 수 있는가 "
    "4) bias_risk: 편향 위험이 얼마나 낮은가 (높을수록 편향 위험이 낮음) "
    "total = clarity*0.2 + mechanism*0.3 + measurability*0.3 + bias_risk*0.2 로 계산하세요. "
    "passed = total >= 70. "
    "weak_axes는 개별 임계값 미달 항목입니다: clarity<60, mechanism<70, measurability<70, bias_risk<60. "
    "rationale에 각 축 점수의 근거를 간결하게 작성하세요. "
    "반드시 QualityScore JSON 스키마로만 답하세요."
)

SYSTEM_SCORE_EN = (
    "You are an A/B test hypothesis quality evaluator. Score the provided hypothesis on "
    "4 axes (0-100): "
    "1) clarity: How clear and specific is the hypothesis statement "
    "2) mechanism: How well is the causal path (intervention→behavior change→metric) explained "
    "3) measurability: Can the primary metric be actually measured "
    "4) bias_risk: How low is the bias risk (higher = less bias risk) "
    "Calculate total = clarity*0.2 + mechanism*0.3 + measurability*0.3 + bias_risk*0.2. "
    "passed = total >= 70. "
    "weak_axes are axes below individual thresholds: clarity<60, mechanism<70, measurability<70, bias_risk<60. "
    "Write a concise rationale for each axis score. "
    "Answer ONLY as QualityScore JSON schema."
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


def score_hypothesis(
    hypothesis: HypothesisOutput,
    service_context: ServiceContext | None,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> QualityScore:
    """가설의 품질 점수를 평가한다.

    결정론적 사전 필터를 먼저 적용한 뒤, LLM이 나머지 축을 점수화한다.

    Args:
        hypothesis: 평가할 가설 출력
        service_context: 서비스 컨텍스트 (없으면 None)
        api_key: LLM API 키
        provider: LLM 제공자
        lang: 언어 코드 (ko/en)
        model: 사용할 모델명. None이면 provider별 기본값 사용.

    Returns:
        QualityScore
    """
    # 결정론적 사전 필터
    pre_mechanism_zero = (
        not hypothesis.mechanism_path or len(hypothesis.mechanism_path.strip()) < 20
    )
    pre_measurability_zero = not hypothesis.measurability_confirmed

    # 프롬프트 구성
    if lang == "ko":
        prompt_parts = [
            f"[가설 정보]",
            f"원 아이디어: {hypothesis.raw_idea}",
            f"정제된 가설: {hypothesis.sharpened_hypothesis}",
            f"메커니즘 경로: {hypothesis.mechanism_path}",
            f"측정 가능 여부: {hypothesis.measurability_confirmed}",
            f"주요 지표: {hypothesis.suggested_primary_metric}",
            f"혼란변수 후보: {', '.join(hypothesis.confounder_candidates)}",
            f"암묵적 전제: {', '.join(hypothesis.implicit_assumptions)}",
        ]
    else:
        prompt_parts = [
            f"[Hypothesis Information]",
            f"Raw Idea: {hypothesis.raw_idea}",
            f"Sharpened Hypothesis: {hypothesis.sharpened_hypothesis}",
            f"Mechanism Path: {hypothesis.mechanism_path}",
            f"Measurability Confirmed: {hypothesis.measurability_confirmed}",
            f"Primary Metric: {hypothesis.suggested_primary_metric}",
            f"Confounder Candidates: {', '.join(hypothesis.confounder_candidates)}",
            f"Implicit Assumptions: {', '.join(hypothesis.implicit_assumptions)}",
        ]

    if pre_mechanism_zero and lang == "ko":
        prompt_parts.append("※ 주의: mechanism_path가 비어 있거나 20자 미만 — mechanism 점수는 0으로 강제됩니다.")
    elif pre_mechanism_zero:
        prompt_parts.append("※ NOTE: mechanism_path is empty or shorter than 20 chars — mechanism score is forced to 0.")

    if pre_measurability_zero and lang == "ko":
        prompt_parts.append("※ 주의: measurability_confirmed=False — measurability 점수는 0으로 강제됩니다.")
    elif pre_measurability_zero:
        prompt_parts.append("※ NOTE: measurability_confirmed=False — measurability score is forced to 0.")

    prompt = "\n".join(prompt_parts)

    # 서비스 컨텍스트 주입
    system = SYSTEM_SCORE_KO if lang == "ko" else SYSTEM_SCORE_EN
    if service_context is not None:
        system = system + _build_context_block(service_context, lang)

    score = call_structured(
        prompt=prompt,
        system=system,
        schema=QualityScore,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )

    # 사전 필터 강제 적용 (LLM이 무시하더라도 덮어씀)
    overrides: dict = {}
    if pre_mechanism_zero:
        overrides["mechanism"] = 0
    if pre_measurability_zero:
        overrides["measurability"] = 0

    if overrides:
        score = score.model_copy(update=overrides)

    # total 재계산 (사전 필터 적용 후)
    total = int(
        score.clarity * 0.2
        + score.mechanism * 0.3
        + score.measurability * 0.3
        + score.bias_risk * 0.2
    )
    weak_axes = get_weak_axes(score)
    passed = total >= 70

    return score.model_copy(update={"total": total, "weak_axes": weak_axes, "passed": passed})


def get_weak_axes(score: QualityScore, threshold: int = 70) -> list[str]:
    """개별 임계값 미달 축 목록을 반환한다.

    임계값 기준:
    - clarity < 60
    - mechanism < 70
    - measurability < 70
    - bias_risk < 60

    Args:
        score: QualityScore 객체
        threshold: 미사용 파라미터 (개별 축마다 고유 임계값 사용). API 호환성을 위해 유지.

    Returns:
        임계값 미달 축 이름 리스트
    """
    weak: list[str] = []
    if score.clarity < 60:
        weak.append("clarity")
    if score.mechanism < 70:
        weak.append("mechanism")
    if score.measurability < 70:
        weak.append("measurability")
    if score.bias_risk < 60:
        weak.append("bias_risk")
    return weak
