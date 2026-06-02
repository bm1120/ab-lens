"""ContextLoopGuard (v8 핵심 해자).

설계 시점의 약속(DesignContext)과 분석 시점의 현실(ObservedResult)을
대조해 통계적 양심을 강제하는 deterministic 가드. LLM 호출이 없으므로
비용 0, 결과가 재현 가능하다.

감지하는 위반:
  - peeking     : 약속 표본에 못 미친 채 결론 시도 (조기 종료)
  - metric_swap : 유의하게 나온 지표가 약속한 1차 지표가 아님 (체리피킹)
  - below_mde   : 관측 효과가 합의 MDE 미만 (실무적 무의미)
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from src.design_schemas import DesignContext


class ObservedResult(BaseModel):
    current_n: int                          # 현재 (양 그룹 합산) 표본 수
    significant_metric: Optional[str]        # 통계적으로 유의하게 나온 지표명 (없으면 None)
    effect: float                            # 관측된 효과 크기 (primary 기준)


class Violation(BaseModel):
    kind: Literal["peeking", "metric_swap", "below_mde"]
    severity: Literal["high", "medium"]
    message: str


def context_loop_guard(
    ctx: Optional[DesignContext], observed: ObservedResult
) -> list[Violation]:
    if ctx is None:
        return []  # 사전 설계 미업로드 → 대조 생략

    violations: list[Violation] = []

    reach = observed.current_n / ctx.target_sample_size
    if reach < 1.0:
        violations.append(
            Violation(
                kind="peeking",
                severity="high",
                message=(
                    f"약속한 표본 {ctx.target_sample_size:,}명의 {reach:.0%}"
                    f"({observed.current_n:,}명)만 도달한 채 결론을 시도하고 있습니다. "
                    "조기 종료(peeking)는 거짓 양성 위험을 키웁니다."
                ),
            )
        )

    if observed.significant_metric is not None and observed.significant_metric != ctx.primary_metric:
        violations.append(
            Violation(
                kind="metric_swap",
                severity="high",
                message=(
                    f"유의하게 나온 지표({observed.significant_metric})가 "
                    f"설계 때 약속한 1차 지표({ctx.primary_metric})와 다릅니다. "
                    "사후 지표 교체는 체리피킹입니다."
                ),
            )
        )

    if observed.effect < ctx.agreed_mde:
        violations.append(
            Violation(
                kind="below_mde",
                severity="medium",
                message=(
                    f"관측 효과({observed.effect:.3f})가 합의 MDE({ctx.agreed_mde:.3f}) "
                    "미만입니다. 통계적으로 유의해도 실무적으로는 무의미할 수 있습니다."
                ),
            )
        )

    return violations
