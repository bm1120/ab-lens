"""T2 — 도메인 주입 / 도메인 구성 질문.

가설 고도화 전에 도메인 맥락(서비스 유형·타겟 사용자·핵심 비즈니스 목표·제약)이 충분한지 판정하고,
부족하면 사용자에게 물을 **도메인 구성 질문**을 생성한다. 답이 모이면 expander/sharpener에 주입.
"""
from __future__ import annotations

from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from src.llm_client import LLMProvider

DomainField = Literal["service_type", "user_segment", "primary_goal", "constraints", "other"]

_LABELS = {
    "ko": {"service_type": "서비스/제품 유형", "user_segment": "타겟 사용자",
           "primary_goal": "핵심 비즈니스 목표·지표", "constraints": "제약(규제·기술·기간)"},
    "en": {"service_type": "Service/product type", "user_segment": "Target users",
           "primary_goal": "Primary business goal/metric", "constraints": "Constraints (regulatory·tech·time)"},
}


class DomainContext(BaseModel):
    service_type: str = ""
    user_segment: str = ""
    primary_goal: str = ""
    constraints: str = ""

    def filled(self) -> bool:
        return any([self.service_type, self.user_segment, self.primary_goal, self.constraints])

    def to_prompt(self, lang: str = "ko") -> str:
        lab = _LABELS.get(lang, _LABELS["ko"])
        rows = [f"- {lab[k]}: {v}" for k, v in
                (("service_type", self.service_type), ("user_segment", self.user_segment),
                 ("primary_goal", self.primary_goal), ("constraints", self.constraints)) if v]
        if not rows:
            return ""
        head = "[도메인 맥락]" if lang == "ko" else "[Domain context]"
        return head + "\n" + "\n".join(rows)


class DomainQuestion(BaseModel):
    field: DomainField
    question: str


class DomainIntake(BaseModel):
    sufficient: bool                              # 도메인 정보가 고도화에 충분한가
    inferred: DomainContext = Field(default_factory=DomainContext)  # 아이디어에서 추론
    questions: list[DomainQuestion] = []          # 부족하면 채울 질문(최대 3)


_SYSTEM = {
    "ko": ("너는 A/B 테스트 가설 고도화를 돕는 도메인 인테이크다. 아이디어에 가설을 날카롭게 만들기 위한 "
           "도메인 맥락(서비스 유형·타겟 사용자·핵심 비즈니스 목표/지표·제약)이 **충분한지** 판정한다. "
           "충분하면 sufficient=true로 두고 inferred를 아이디어 근거로 채운다. 부족하면 sufficient=false + "
           "**부족한 필드만** 묻는 질문을 최대 3개(각 한 문장, 사용자가 바로 답할 수 있게). 추측으로 메우지 마라."),
    "en": ("You are a domain intake for A/B test hypothesis refinement. Decide whether the idea has **enough** "
           "domain context (service type, target users, primary business goal/metric, constraints) to sharpen a "
           "hypothesis. If enough, sufficient=true and fill inferred from the idea. If not, sufficient=false and ask "
           "up to 3 one-sentence questions for the **missing fields only**. Do not fabricate."),
}


def analyze_domain(
    idea: str,
    existing: Optional[DomainContext] = None,
    *,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: Optional[str] = None,
    _call: Optional[Callable] = None,
) -> DomainIntake:
    """도메인 충분성 판정 + 부족 필드 질문 생성. existing(사용자가 이미 준 맥락) 있으면 반영."""
    ctx = (existing.to_prompt(lang) + "\n\n") if (existing and existing.filled()) else ""
    prompt = f"{ctx}아이디어: {idea}" if lang == "ko" else f"{ctx}Idea: {idea}"
    if _call is None:
        from src.llm_json import call_structured
        _call = call_structured
    try:
        return _call(prompt=prompt, system=_SYSTEM.get(lang, _SYSTEM["ko"]),
                     schema=DomainIntake, api_key=api_key, provider=provider, lang=lang, model=model)
    except Exception as e:
        # 실패 시 보수적: 충분하다고 보고 진행(질문 없이) — 고도화 자체를 막지 않음
        import logging
        logging.getLogger(__name__).warning("domain intake 실패 → 질문 생략하고 진행: %s", e)
        return DomainIntake(sufficient=True, inferred=existing or DomainContext(), questions=[])


def context_from_answers(questions: list[DomainQuestion], answers: dict[str, str],
                         base: Optional[DomainContext] = None) -> DomainContext:
    """질문-답변(field→답) 을 DomainContext로. base(추론/기존)에 덮어쓴다."""
    ctx = (base.model_copy() if base else DomainContext())
    for q in questions:
        a = (answers.get(q.field) or "").strip()
        if not a:
            continue
        if q.field == "other":
            ctx.constraints = (ctx.constraints + " / " + a).strip(" /")
        else:
            setattr(ctx, q.field, a)
    return ctx
