"""조작적 정의화 (operationalization).

추상 구성개념을 측정지표로 내린다. 핵심 제약(3-모델 리뷰):
- 후보 metric_type 은 탭2 통계엔진 호환 3종(proportion/continuous/count)으로 **강제**.
- 설문/시계열/장기 귀인처럼 A/B로 직접 측정 어려운 건 ab_testable=False + incompatible_note.
지표 선택권은 LLM이 아니라 사용자에게 있다(후보 제안만) → PinnedMetrics 로 확정.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from src.hypothesis.measurement_prompt import SYSTEM_KO, SYSTEM_EN
from src.llm_json import call_structured
from src.schemas import LLMProvider


class MetricCandidate(BaseModel):
    label: str
    metric_type: Literal["proportion", "continuous", "count"]  # 탭2 호환 강제
    ab_testable: bool = True
    rationale: str = ""


class ConstructMeasurement(BaseModel):
    construct_name: str                 # 'construct'는 BaseModel 속성과 충돌 → _name
    conceptual_definition: str          # 사용자 편집 대상
    candidates: list[MetricCandidate]
    incompatible_note: str = ""         # 비호환 지표·인과대안 안내
    proxy_warning: str = ""             # 단기 행동지표가 장기 구성개념의 대리일 때 Goodhart 경고


class MeasurementProposal(BaseModel):
    measurements: list[ConstructMeasurement]
    needs_question: bool = False        # 도메인 부족 → "모르겠음" 경로
    question: str = ""


class PinnedMetrics(BaseModel):
    """사용자 확정 지표 → sharpener 에 고정 주입(LLM 재선택 금지)."""

    primary_metric: str
    secondary_metrics: list[str] = []


def _build_prompt(idea: str, constructs: list[str], domain_context: str) -> str:
    return (
        f"아이디어: {idea}\n"
        f"추상 구성개념: {', '.join(constructs)}\n"
        f"도메인 맥락: {domain_context or '(미제공)'}\n"
        "각 구성개념에 개념적 정의와, 측정 가능한 지표 후보를 제시하라."
    )


# A/B로 직접 측정 어려운 신호 → 후처리로 ab_testable=False 강제 (리뷰 A: LLM이 3종에 끼워맞춤 방지)
_INCOMPAT_SIGNALS = (
    "설문", "survey", "recall", "회상", "장기", "long-term", "long term",
    "brand lift", "브랜드 리프트", "cross-channel", "크로스채널", "attribution",
    "귀인", "nps", "리커트", "likert", "self-report", "자기보고",
)
_FALLBACK_Q = "어떤 채널·이벤트로 측정할 수 있나요? (예: 사이트 내 검색 / 광고 클릭 / 직접 방문 / 재구매)"


def _post_process(proposal: MeasurementProposal, domain_context: str) -> MeasurementProposal:
    """리뷰 반영: 비호환 신호 → ab_testable=False 강제 + needs_question deterministic 보정."""
    for cm in proposal.measurements:
        for c in cm.candidates:
            blob = f"{c.label} {c.rationale}".lower()
            if any(sig.lower() in blob for sig in _INCOMPAT_SIGNALS):
                c.ab_testable = False
    has_incompat = any(not c.ab_testable for cm in proposal.measurements for c in cm.candidates)
    # 도메인 맥락이 없거나 비호환 후보가 섞이면 멀티턴 질문 트리거(LLM 자기판단에만 의존 안 함)
    if not domain_context.strip() or has_incompat:
        proposal.needs_question = True
        if not proposal.question.strip():
            proposal.question = _FALLBACK_Q
    return proposal


def propose_measurement(
    idea: str,
    constructs: list[str],
    domain_context: str = "",
    *,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: Optional[str] = None,
) -> MeasurementProposal:
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    try:
        proposal = call_structured(
            prompt=_build_prompt(idea, constructs, domain_context),
            system=system, schema=MeasurementProposal,
            api_key=api_key, provider=provider, lang=lang, model=model,
        )
    except Exception:
        # graceful degradation: 크래시 대신 사용자에게 무엇이 필요한지 되묻기 (리뷰 B)
        return MeasurementProposal(measurements=[], needs_question=True, question=_FALLBACK_Q)
    return _post_process(proposal, domain_context)
