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
    return call_structured(
        prompt=_build_prompt(idea, constructs, domain_context),
        system=system, schema=MeasurementProposal,
        api_key=api_key, provider=provider, lang=lang, model=model,
    )
