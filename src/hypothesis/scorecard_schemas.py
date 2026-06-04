"""HQS(가설품질 스코어카드) 스키마.

LLM judge는 **점수를 생성하지 않고 룰 가이드 Y/P/N 판정 + 1줄 근거만** 낸다(재현성).
점수 매핑은 quality_scorecard.py의 결정론 룰이 담당.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

YPN = Literal["Y", "P", "N"]
YN = Literal["Y", "N"]
_VERDICT_FIELDS = ("falsifiable", "mechanism_plausible", "clarity",
                   "confound_relevant", "tradeoff_real", "alt_justified")


class LLMJudgment(BaseModel):
    """룰 가이드 LLM 판정 (턴당 1회). 각 필드의 판정 규칙은 JUDGE_PROMPT 참조.

    모든 판정 필드는 **비관적 기본값 "N"** + 잘못된 값(소문자·"yes"·범위밖 "P" 등) 강제 보정 →
    LLM이 필드 누락/오출력해도 Pydantic crash 없이 보수적으로 처리(cross_verify 지적 반영).
    """

    # D2 반증가능성 (게이트) — "틀렸다 관측 1문장" 가능할 때만 Y
    falsifiable: YN = "N"
    falsify_scenario: str = ""
    # D3 인과 메커니즘
    mechanism_plausible: YPN = "N"
    mechanism_gap: str = ""
    # D6 명료성
    clarity: YPN = "N"
    clarity_issue: str = ""
    # D4 측정정렬·리스크 — 관련성 판정(개수 아님). tradeoff_real도 YPN 허용(P→0 매핑, crash 방지)
    confound_relevant: YPN = "N"
    tradeoff_real: YPN = "N"
    risk_issue: str = ""
    # D5 대안탐색
    alt_justified: YPN = "N"
    alt_issue: str = ""

    @field_validator(*_VERDICT_FIELDS, mode="before")
    @classmethod
    def _coerce_verdict(cls, v):
        """LLM이 'yes'/'no'/소문자/공백 등을 내도 Y/P/N으로 보정. 불명은 보수적으로 N."""
        if not isinstance(v, str):
            return "N"
        s = v.strip().upper()
        if s in ("Y", "P", "N"):
            return s
        if s in ("YES", "TRUE"):
            return "Y"
        if s in ("PARTIAL", "MAYBE"):
            return "P"
        return "N"


class DimScore(BaseModel):
    score: int
    max: int
    is_gate: bool = False
    passed: bool = True                  # 게이트/통과조건 충족 여부
    note: str = ""


Grade = Literal["PASS", "ACCEPTABLE_CAVEAT", "REFINE", "REDESIGN"]


class ScorecardResult(BaseModel):
    scores: dict[str, DimScore]
    total: int
    gate_passed: bool
    grade: Grade
    failed_set: list[str] = Field(default_factory=list)        # 통과조건 미달 차원
    failed_rule_dims: list[str] = Field(default_factory=list)  # 룰만 미달 (정체 보조신호)
    caveats: list[str] = Field(default_factory=list)
