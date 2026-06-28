"""멀티모델 토론 스키마 (synthesis.md 설계안 기준).

3모델이 독립 추론 → 교차 비평 → Opus 합성.
핵심: DivergencePoint가 1급 필드 — "어디서 왜 갈렸나"가 시그니처.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from src.design_schemas import HypothesisOutput
from src.hypothesis.scorecard_schemas import ScorecardResult


class ModelRole(str, Enum):
    CLAUDE = "claude"
    GPT = "gpt"
    GEMINI = "gemini"


class DraftAttempt(BaseModel):
    """Phase 1: 한 모델의 독립안."""
    role: ModelRole
    model_id: str                           # 실제 사용한 모델 ID
    hypothesis: Optional[HypothesisOutput] = None  # 실패 시 None
    scorecard: Optional[ScorecardResult] = None    # 독립안 채점 (검증용 — 선택엔 안 씀)
    error: Optional[str] = None             # 실패 사유
    elapsed_ms: int = 0


class Critique(BaseModel):
    """Phase 2: critic_role가 target_role의 안을 비평. 타겟별로 분리 생성."""
    critic_role: ModelRole
    target_role: ModelRole
    strengths: list[str]                    # 내 안보다 명백히 나은 점 (없으면 빈 배열)
    weaknesses: list[str]                   # D1측정/D2반증/인과경로 중 어디가 약한가
    steal_worthy: list[str]                 # 흡수할 구체 요소 (필드명 명시)
    fatal_flaw: Optional[str] = None        # 치명적 결함 1개. D1/D2 기준. 없으면 None


class DivergencePoint(BaseModel):
    """모델들이 갈라진 축. Phase 3 합성자가 채워 넣음. UI 시그니처 탭."""
    axis: str                               # "primary_metric" | "mechanism_path" | ...
    positions: dict[str, str]               # role.value → 이 축에서의 입장 요약
    why_it_matters: str                     # 이 불일치가 실험설계상 어떤 위험인지
    verdict: str                            # 합성자가 어느 입장을 왜 채택/기각했는지


class SynthesisOutput(BaseModel):
    """Phase 3 합성 결과."""
    final_hypothesis: HypothesisOutput
    final_scorecard: Optional[ScorecardResult] = None
    absorbed_from: dict[str, str]           # 필드명 → ModelRole.value (필드 단위 출처)
    rejected_with_reason: dict[str, str]    # 버린 요소 → 이유
    divergence_verdicts: list[DivergencePoint]  # 합성자가 도출+판정
    synthesis_rationale: str                # "왜 짜깁기가 아닌가" 자기변론


class DebateResult(BaseModel):
    """멀티모델 토론 전체 결과."""
    idea: str
    drafts: list[DraftAttempt]              # Phase 1 전체 (실패 포함)
    critiques: list[Critique]               # Phase 2 전체 (N×(N-1)개)
    synthesis: SynthesisOutput              # Phase 3

    survived_count: int                     # Phase 1 생존 모델 수
    degraded: bool                          # 실패로 축소 실행 여부
    early_exit_unanimous: bool = False      # 만장일치 조기종료 여부
    total_elapsed_ms: int = 0

    @property
    def winning_hypothesis(self) -> HypothesisOutput:
        return self.synthesis.final_hypothesis
