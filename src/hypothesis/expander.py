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
    domain: str | None = None,
) -> ExpanderOutput:
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    prompt = f"{domain}\n\n아이디어: {idea}" if domain else idea
    return call_structured(
        prompt=prompt,
        system=system,
        schema=ExpanderOutput,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )
