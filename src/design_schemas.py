"""탭1(가설 고도화·설계)과 Context Loop를 위한 공통 스키마 (v8 Task D).

기존 src/schemas.py(탭2 결과분석)와 분리한다. 거기에도 BiasItem 이 있어
이름이 충돌하기 때문이다. 여기 BiasScreenItem 은 '설계 시점' 편향 스크리닝용.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel

from src.bias_pool import BiasType

# DesignContext 직렬화 호환성 버전. 구조가 바뀌면 올린다.
SCHEMA_VERSION = "9.0"


class ServiceContext(BaseModel):
    """서비스 컨텍스트 — 가설 검증 전 수집하는 제품/서비스 배경 정보."""

    service_name: str
    target_users: str
    primary_metric: str
    current_baseline: str
    past_experiments: str
    domain_constraints: str


class QualityScore(BaseModel):
    """가설 품질 점수 — 4개 축 + 가중 총점 + 통과 여부."""

    clarity: int        # 0-100
    mechanism: int      # 0-100
    measurability: int  # 0-100
    bias_risk: int      # 0-100 (높을수록 편향 위험 낮음, inverted)
    total: int          # weighted: clarity*0.2 + mechanism*0.3 + measurability*0.3 + bias_risk*0.2
    weak_axes: list[str]
    passed: bool        # total >= 70
    rationale: str


class RejectedAlternative(BaseModel):
    hypothesis: str
    rejection_reason: str                # "측정 불가 / 편향 과다 / 팀 합의와 충돌"


class HypothesisOutput(BaseModel):
    """탭1 가설 고도화 결과 = 통계 파라미터로 1:1 매핑되는 구조화 출력."""

    raw_idea: str
    jtbd_reframe: str
    implicit_assumptions: list[str]
    mechanism_path: str                  # "개입 → 행동 변화 → 지표" 명시
    confounder_candidates: list[str]
    measurability_confirmed: bool
    sharpened_hypothesis: str
    suggested_primary_metric: str
    suggested_secondary_metrics: list[str]
    predicted_tradeoff_metrics: list[str]
    experiment_feasible: bool
    causal_alternative: Optional[str] = None   # 불가 시 DiD/PSM 조건
    rejected_alternatives: list[RejectedAlternative] = []


class BiasScreenItem(BaseModel):
    bias_type: BiasType                  # 풀 7종 외 값 구조적 불가
    status: Literal["active", "latent", "not_applicable"]
    evidence: str
    counter_measure: str


class BiasScreenResult(BaseModel):
    biases: list[BiasScreenItem]
    active_count: int
    warning_only: bool = True            # 블로킹 없음, Warning만


class DesignQuality(BaseModel):
    required_pass: bool                  # 필수 항목 통과 여부
    required_items: dict[str, bool]      # metric, randomization_unit
    advisory_score: int                  # 0~100 권고 점수
    advisory_items: dict[str, bool]      # 권고 항목 통과 여부
    # 강제 차단 없음 — advisory_score < 50 이면 강한 경고만


class SamplePlanOutput(BaseModel):
    metric_type: Literal["proportion", "continuous", "count"]
    per_group: int                       # design effect 반영된 그룹당 표본
    total: int                           # per_group * 2
    design_effect: float = 1.0           # cluster 시 1 + (m-1)*icc
    assumptions: dict[str, float]        # baseline/mde/alpha/power/std_dev 등 입력 기록


class DesignContext(BaseModel):
    """탭1 설계 결과 = 탭2로 넘기는 '약속'. ab-design-context.json 으로 이월."""

    schema_version: str = SCHEMA_VERSION
    sharpened_hypothesis: str
    primary_metric: str
    metric_type: Literal["proportion", "continuous", "count"]
    agreed_mde: float
    baseline: float
    std_dev: Optional[float] = None
    alpha: float = 0.05
    power: float = 0.8
    target_sample_size: int
    experiment_duration_days: int
    randomization_unit: Literal["user", "session", "device", "cluster"]
    icc: Optional[float] = None
    stop_criteria: str
    design_quality: DesignQuality
    bias_screening_summary: str          # 탭2 편향 교차 참조용
    alternative_selected: Optional[str] = None
    service_context: Optional[ServiceContext] = None

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str | bytes) -> "DesignContext":
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"malformed design context json: {e}") from e
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"incompatible schema version: {version!r} (expected {SCHEMA_VERSION!r})"
            )
        return cls.model_validate(data)
