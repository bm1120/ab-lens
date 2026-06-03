"""Trivial Router (Stage 0) — A/B 테스트 대상이 아닌 사소한 변경을 걸러낸다.

버그픽스/오타수정/단순 문구 변경 등은 실험 없이 그냥 적용("Just Do It")하면 된다.
실험 비용 낭비를 막는 첫 관문.
"""
from __future__ import annotations

from pydantic import BaseModel

from src.llm_json import call_structured
from src.schemas import LLMProvider

SYSTEM_KO = (
    "당신은 A/B 테스트 설계 게이트키퍼입니다. 사용자의 아이디어가 A/B 테스트로 검증할 "
    "가치가 있는지 판정하세요. 버그 수정, 오타/문구 정정, 명백한 개선(접근성/법적 의무), "
    "측정 불가능한 변경은 '사소함(trivial)'으로 분류하고 'Just Do It'을 권합니다. "
    "사용자 행동·전환에 영향을 줄 수 있는 변경은 사소하지 않습니다. "
    '반드시 JSON으로만 답하세요: {"is_trivial": bool, "reason": "한국어 한 문장"}'
)
SYSTEM_EN = (
    "You are an A/B test design gatekeeper. Decide whether the user's idea is worth "
    "validating via an A/B test. Bug fixes, typo/copy corrections, obviously-correct "
    "changes (accessibility/legal), and unmeasurable changes are 'trivial' → recommend "
    "'Just Do It'. Changes that could affect user behavior/conversion are NOT trivial. "
    'Answer ONLY as JSON: {"is_trivial": bool, "reason": "one sentence"}'
)


class TrivialVerdict(BaseModel):
    is_trivial: bool
    reason: str


def route_trivial(
    idea: str,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> TrivialVerdict:
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    return call_structured(
        prompt=idea,
        system=system,
        schema=TrivialVerdict,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )
