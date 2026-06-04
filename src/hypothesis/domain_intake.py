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


def _san(v: str) -> str:
    """프롬프트 인젝션·포맷깨짐 방어: 개행 제거 + 길이 제한."""
    return " ".join(str(v or "").split())[:300]


class DomainContext(BaseModel):
    service_type: str = ""
    user_segment: str = ""
    primary_goal: str = ""
    constraints: str = ""
    other_info: str = ""                 # 기타 참고(경쟁사·과거사례 등) — constraints와 분리

    _FIELDS = ("service_type", "user_segment", "primary_goal", "constraints")

    def filled(self) -> bool:
        return any(getattr(self, f) for f in self._FIELDS) or bool(self.other_info)

    def missing_fields(self) -> set[str]:
        return {f for f in self._FIELDS if not getattr(self, f)}

    def merged_with(self, other: "DomainContext") -> "DomainContext":
        """self가 우선, 빈 필드는 other(추론값)로 채움."""
        return DomainContext(**{f: (getattr(self, f) or getattr(other, f))
                                for f in self._FIELDS + ("other_info",)})

    def to_prompt(self, lang: str = "ko") -> str:
        lab = _LABELS.get(lang, _LABELS["ko"])
        rows = [f"- {lab[k]}: {_san(v)}" for k, v in
                (("service_type", self.service_type), ("user_segment", self.user_segment),
                 ("primary_goal", self.primary_goal), ("constraints", self.constraints)) if v]
        if self.other_info:
            rows.append(("- 기타 참고: " if lang == "ko" else "- Other notes: ") + _san(self.other_info))
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
    "ko": ("너는 A/B 테스트 가설 고도화를 돕는 도메인 인테이크다. 아이디어에서 도메인 맥락"
           "(서비스 유형·타겟 사용자·핵심 비즈니스 목표/지표·제약)을 **합리적으로 추론해 inferred를 최대한 채워라.** "
           "추론으로 충분하면 sufficient=true. **추론조차 불가능해 A/B 설계를 진행할 수 없는 치명적 누락이 있을 때만** "
           "sufficient=false로 하고, 그 누락 필드만 묻는 질문을 **최대 2개**(각 한 문장) 생성한다. 사소한 보강 질문으로 사용자를 귀찮게 하지 마라."),
    "en": ("You are a domain intake for A/B test hypothesis refinement. **Infer the domain context** "
           "(service type, target users, primary goal/metric, constraints) from the idea and fill `inferred` as much as possible. "
           "If inference suffices, sufficient=true. **Only when a critical gap makes A/B design impossible even after inference**, "
           "set sufficient=false and ask **at most 2** one-sentence questions for those gaps. Do not nag with minor clarifications."),
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
            ctx.other_info = (ctx.other_info + " / " + a).strip(" /")
        else:
            setattr(ctx, q.field, a)
    return ctx
