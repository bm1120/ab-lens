from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    CLAUDE_CODE = "claude_code"  # Claude Code 구독 OAuth 토큰 (비용 0)


class ABTestInput(BaseModel):
    metric_name: str = Field(..., description="측정 메트릭 이름 (예: 전환율, 클릭율)")
    treatment_value: float = Field(..., description="Treatment 그룹 메트릭 값 (비율, 0~1)")
    control_value: float = Field(..., description="Control 그룹 메트릭 값 (비율, 0~1)")
    p_value: float = Field(..., description="실험에서 계산된 p-value")
    sample_size_treatment: int = Field(..., description="Treatment 그룹 샘플 수")
    sample_size_control: int = Field(..., description="Control 그룹 샘플 수")
    experiment_days: int = Field(..., description="실험 진행 일수")
    dev_cost_weeks: Optional[float] = Field(None, description="개발 비용 (주 단위)")
    business_priority: Optional[Literal["high", "medium", "low"]] = Field(None, description="비즈니스 우선순위")
    prior_expectation: Optional[str] = Field(None, description="실험 전 기대값 또는 가설")
    is_random_assignment: bool = Field(True, description="무작위 배정 여부")
    multiple_metrics: bool = Field(False, description="다중 메트릭 동시 테스트 여부")
    business_context: Optional[str] = Field(None, description="비즈니스 맥락 및 추가 정보")
    provider: LLMProvider = Field(LLMProvider.ANTHROPIC, description="LLM 제공자 (anthropic/openrouter)")


class StatisticalResult(BaseModel):
    effect_size_pp: float = Field(..., description="효과 크기 (percentage points, treatment - control)")
    effect_size_relative_pct: float = Field(..., description="상대적 효과 크기 (%)")
    is_significant: bool = Field(..., description="통계적 유의성 여부 (p < 0.05)")
    power_pct: float = Field(..., description="검정력 (%)")
    srm_detected: bool = Field(..., description="Sample Ratio Mismatch 감지 여부")
    srm_detail: Optional[str] = Field(None, description="SRM 상세 정보")
    additional_sample_needed: Optional[int] = Field(None, description="80% 검정력 달성에 필요한 추가 샘플 수")
    interpretation: str = Field(..., description="원시 통계 수치 요약")


class BiasItem(BaseModel):
    name: str = Field(..., description="편향 이름")
    severity: Literal["low", "medium", "high"] = Field(..., description="심각도")
    description: str = Field(..., description="편향 설명 및 발현 양상")
    counter: str = Field(..., description="대응 방법")
    paper_reference: Optional[str] = Field(None, description="논문 근거")


class BiasReport(BaseModel):
    biases: list[BiasItem] = Field(..., description="감지된 편향 목록")
    overall_risk: Literal["low", "medium", "high"] = Field(..., description="전체 위험도")


class CausalAlt(BaseModel):
    experiment_feasible: bool = Field(..., description="실험 설계 실현 가능 여부")
    alternative_method: Optional[str] = Field(None, description="대안적 인과추론 방법")
    method_description: Optional[str] = Field(None, description="방법 설명")


class Scenario(BaseModel):
    name: str = Field(..., description="시나리오 이름")
    probability_pct: int = Field(..., description="시나리오 발생 확률 (%)")
    pros: list[str] = Field(..., description="장점 목록")
    cons: list[str] = Field(..., description="단점 목록")
    risk_level: Literal["low", "medium", "high"] = Field(..., description="위험도")


class Recommendation(BaseModel):
    scenarios: list[Scenario] = Field(..., description="시나리오 목록")
    final_recommendation: str = Field(..., description="최종 추천 행동")
    confidence_pct: int = Field(..., description="추천 신뢰도 (%)")
    rationale: str = Field(..., description="추천 근거")


class BriefOutput(BaseModel):
    statistical: StatisticalResult
    bias_report: BiasReport
    causal_alt: Optional[CausalAlt] = None
    recommendation: Recommendation
    lang: str = Field(default="ko", description="출력 언어 (ko/en)")
