"""HypothesisOutput + 사용자 사실수치 → DesignContext 조립 (deterministic).

수치=사용자입력 불변 원칙: target_sample_size 는 calculate_sample_size 로 계산하고,
LLM 이 만든 가설 텍스트와 사용자가 입력한 사실수치를 결합만 한다.
DesignAgent 의 LLM 지표검토(Goodhart/FWER 코멘트)는 추후 확장.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from src.design_rubric import ADVISORY_ITEMS, grade, score_advisory
from src.design_schemas import (
    BiasScreenResult,
    DesignContext,
    DesignQuality,
    HypothesisOutput,
    MetricReview,
)
from src.design_stats import calculate_sample_size


class DesignFacts(BaseModel):
    """사용자가 입력하는 사실수치 (LLM 이 만들지 않음)."""

    metric_type: Literal["proportion", "continuous", "count"]
    baseline: float
    agreed_mde: float
    std_dev: Optional[float] = None
    alpha: float = 0.05
    power: float = 0.8
    randomization_unit: Literal["user", "session", "device", "cluster"] = "user"
    experiment_duration_days: int = 14
    icc: Optional[float] = None
    stop_criteria: str = "목표 표본 도달 시 종료, 중간 peeking 금지"


def _build_quality(hyp: HypothesisOutput, facts: DesignFacts, sample: int) -> DesignQuality:
    required = {
        "primary_metric_defined": bool(hyp.suggested_primary_metric),
        "randomization_unit_clear": bool(facts.randomization_unit),
    }
    advisory = {
        "hypothesis_sharpened": bool(hyp.sharpened_hypothesis),
        "mechanism_path_clear": bool(hyp.mechanism_path),
        "mde_business_meaningful": facts.agreed_mde > 0,
        "sufficient_sample_size": sample > 0,
        "stop_criteria_agreed": bool(facts.stop_criteria),
        "srm_prevention_checked": facts.randomization_unit in ("user", "session", "device", "cluster"),
        "secondary_metrics_bounded": len(hyp.suggested_secondary_metrics) <= 3,
    }
    # 룰브릭에 정의된 키만 채점에 사용
    advisory = {k: advisory.get(k, False) for k in ADVISORY_ITEMS}
    return DesignQuality(
        required_pass=all(required.values()),
        required_items=required,
        advisory_score=score_advisory(advisory),
        advisory_items=advisory,
    )


def assemble_design_context(
    hyp: HypothesisOutput,
    bias: BiasScreenResult,
    facts: DesignFacts,
    metric_review: Optional[MetricReview] = None,
) -> DesignContext:
    sample = calculate_sample_size(
        metric_type=facts.metric_type,
        baseline=facts.baseline,
        mde=facts.agreed_mde,
        alpha=facts.alpha,
        power=facts.power,
        std_dev=facts.std_dev,
        icc=facts.icc,
    )
    active = [b for b in bias.biases if b.status == "active"]
    summary = "; ".join(f"{b.bias_type}: {b.evidence}" for b in active) or "활성 편향 없음"
    quality = _build_quality(hyp, facts, sample.total)
    return DesignContext(
        sharpened_hypothesis=hyp.sharpened_hypothesis,
        primary_metric=hyp.suggested_primary_metric,
        metric_type=facts.metric_type,
        agreed_mde=facts.agreed_mde,
        baseline=facts.baseline,
        std_dev=facts.std_dev,
        alpha=facts.alpha,
        power=facts.power,
        target_sample_size=sample.total,
        experiment_duration_days=facts.experiment_duration_days,
        randomization_unit=facts.randomization_unit,
        icc=facts.icc,
        stop_criteria=facts.stop_criteria,
        design_quality=quality,
        bias_screening_summary=summary,
        alternative_selected=hyp.raw_idea if False else None,
        metric_review=metric_review,
    )


def quality_grade(ctx: DesignContext) -> str:
    return grade(ctx.design_quality.advisory_score)
