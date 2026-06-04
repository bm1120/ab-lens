"""HQS(가설품질 스코어카드) 스키마.

LLM judge는 **점수를 생성하지 않고 룰 가이드 Y/P/N 판정 + 1줄 근거만** 낸다(재현성).
점수 매핑은 quality_scorecard.py의 결정론 룰이 담당.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

YPN = Literal["Y", "P", "N"]
YN = Literal["Y", "N"]


class LLMJudgment(BaseModel):
    """룰 가이드 LLM 판정 (턴당 1회). 각 필드의 판정 규칙은 JUDGE_PROMPT 참조."""

    # D2 반증가능성 (게이트) — 룰 가이드: "틀렸다 관측 1문장" 가능할 때만 Y
    falsifiable: YN
    falsify_scenario: str = ""           # Y면 그 관측 1문장, N이면 ""

    # D3 인과 메커니즘 — 화살표 하나씩 검사
    mechanism_plausible: YPN
    mechanism_gap: str = ""              # P/N이면 끊긴 링크 지적

    # D6 명료성
    clarity: YPN
    clarity_issue: str = ""

    # D4 측정정렬·리스크 (개수 아님 — 관련성 판정으로 전환, 진단 결과 반영)
    confound_relevant: YPN               # 처치배정 AND 지표 둘 다 영향 ≥2개=Y
    tradeoff_real: YN                    # 1차지표 개선 시 악화할 가드레일 실재=Y
    risk_issue: str = ""

    # D5 대안탐색 — 실질 사유 여부
    alt_justified: YPN                   # rejected에 실질 사유 ≥1=Y, 빈약=P, 없음=N
    alt_issue: str = ""


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
