"""구성개념 분류 — 추상(측정 타당도 확인 필요) vs 명확(빠른 경로).

라우팅 결정이므로 Haiku temp=0(결정론). 불확실/오류는 'mixed'로 보수 편향:
거짓음성(추상을 명확으로 처리 → 무효 지표 통과)이 거짓양성보다 비용이 크다(3-모델 리뷰).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator

from src.hypothesis.classify_prompt import SYSTEM_KO, SYSTEM_EN
from src.llm_client import judge_model_for
from src.llm_json import call_structured
from src.schemas import LLMProvider

ConstructKind = Literal["clear", "abstract", "mixed"]


class ConstructClassification(BaseModel):
    kind: ConstructKind = "mixed"
    constructs: list[str] = []      # 추상 구성개념명 (clear면 빈 리스트)
    rationale: str = ""             # 사용자에게 보여줄 근거 1~2문장

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v):
        s = str(v).strip().lower()
        return s if s in ("clear", "abstract", "mixed") else "mixed"


def classify_construct(
    idea: str,
    *,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: Optional[str] = None,
) -> ConstructClassification:
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    eff_model = model or judge_model_for(provider)  # 결정론 Haiku
    try:
        return call_structured(
            prompt=idea, system=system, schema=ConstructClassification,
            api_key=api_key, provider=provider, lang=lang,
            model=eff_model, temperature=0.0,
        )
    except Exception:
        # 분류 실패 → 측정 확인 쪽으로 (안전)
        return ConstructClassification(kind="mixed", rationale="분류 실패 — 측정 확인 진행")
