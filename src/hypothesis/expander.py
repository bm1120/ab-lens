"""HypothesisExpander (Stage 1) — Framer + Ideator 통합.

아이디어를 JTBD로 재프레이밍하고 암묵적 전제를 드러낸 뒤, 대안 가설을 발산한다.
이 단계는 '발산'이므로 후보를 평가하거나 수렴시키지 않는다(그건 Sharpener의 몫).
A/B 특화 제약: 측정 가능한 개입만 후보로.
"""
from __future__ import annotations

from pydantic import BaseModel

from src.llm_json import call_structured
from src.schemas import LLMProvider

SYSTEM_KO = (
    "당신은 A/B 테스트 가설 발산 전문가입니다. 사용자의 거친 아이디어를 받아: "
    "(1) JTBD(Jobs To Be Done) 형식으로 재프레이밍하고, "
    "(2) 숨은 암묵적 전제를 드러내며, "
    "(3) 측정 가능한 개입에 한해 서로 다른 대안 가설 3개를 발산합니다. "
    "이 단계에서는 평가·수렴하지 마세요(발산만). "
    "jtbd_reframe 은 반드시 'When [상황], I want to [목표], so I can [결과]' 형식의 "
    "완전한 문장으로 작성하세요. "
    "예시: 'When 사용자가 CTA 버튼을 봤을 때, I want to 즉각적으로 클릭하고 싶다, "
    "so I can 원하는 정보에 빠르게 도달할 수 있다.' "
    '반드시 JSON으로만 답하세요: {"jtbd_reframe": str, "implicit_assumptions": [str], '
    '"candidate_hypotheses": [str, str, str]}'
)
SYSTEM_EN = (
    "You are an A/B test hypothesis diverger. Given a rough idea: "
    "(1) reframe it as a JTBD statement, (2) surface hidden implicit assumptions, "
    "(3) diverge into 3 distinct alternative hypotheses, limited to measurable "
    "interventions. Do NOT evaluate or converge at this stage. "
    'Answer ONLY as JSON: {"jtbd_reframe": str, "implicit_assumptions": [str], '
    '"candidate_hypotheses": [str, str, str]}'
)


def _service_context_block(service_context: object, lang: str) -> str:
    """ServiceContext를 시스템 프롬프트에 주입할 텍스트 블록으로 변환한다."""
    if lang == "ko":
        return (
            "\n\n[서비스 컨텍스트 — 발산 시 반드시 반영]\n"
            f"서비스명: {service_context.service_name}\n"  # type: ignore[union-attr]
            f"타깃 사용자: {service_context.target_users}\n"  # type: ignore[union-attr]
            f"주요 지표: {service_context.primary_metric}\n"  # type: ignore[union-attr]
            f"현재 베이스라인: {service_context.current_baseline}\n"  # type: ignore[union-attr]
            f"과거 실험: {service_context.past_experiments}\n"  # type: ignore[union-attr]
            f"도메인 제약: {service_context.domain_constraints}"  # type: ignore[union-attr]
        )
    return (
        "\n\n[Service Context — must reflect in divergence]\n"
        f"Service Name: {service_context.service_name}\n"  # type: ignore[union-attr]
        f"Target Users: {service_context.target_users}\n"  # type: ignore[union-attr]
        f"Primary Metric: {service_context.primary_metric}\n"  # type: ignore[union-attr]
        f"Current Baseline: {service_context.current_baseline}\n"  # type: ignore[union-attr]
        f"Past Experiments: {service_context.past_experiments}\n"  # type: ignore[union-attr]
        f"Domain Constraints: {service_context.domain_constraints}"  # type: ignore[union-attr]
    )


class ExpanderOutput(BaseModel):
    jtbd_reframe: str
    implicit_assumptions: list[str]
    candidate_hypotheses: list[str]


def expand(
    idea: str,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
    service_context: object | None = None,
) -> ExpanderOutput:
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    if service_context is not None:
        system = system + _service_context_block(service_context, lang)
    return call_structured(
        prompt=idea,
        system=system,
        schema=ExpanderOutput,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )
