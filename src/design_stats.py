"""설계 시점 표본 크기 계산 (deterministic tool, 지표 타입 3종).

수치는 사용자 입력(baseline/std_dev/트래픽)으로만 계산한다. LLM 추정 아님.
proportion/continuous 는 statsmodels, count(포아송)는 정규 근사를 쓴다.
"""
from __future__ import annotations

import math
from typing import Literal, Optional

from scipy.stats import norm
from statsmodels.stats.power import NormalIndPower, TTestIndPower
from statsmodels.stats.proportion import proportion_effectsize

from src.design_schemas import SamplePlanOutput


def calculate_sample_size(
    metric_type: Literal["proportion", "continuous", "count"],
    baseline: float,
    mde: float,
    alpha: float = 0.05,
    power: float = 0.8,
    std_dev: Optional[float] = None,
    icc: Optional[float] = None,
    cluster_size: int = 10,
) -> SamplePlanOutput:
    if mde <= 0:
        raise ValueError("mde must be positive")

    if metric_type == "proportion":
        p2 = baseline + mde
        effect = abs(proportion_effectsize(p2, baseline))
        per_group_base = NormalIndPower().solve_power(
            effect_size=effect, alpha=alpha, power=power, alternative="two-sided"
        )
    elif metric_type == "continuous":
        if std_dev is None or std_dev <= 0:
            raise ValueError("continuous metric requires positive std_dev")
        effect = mde / std_dev
        per_group_base = TTestIndPower().solve_power(
            effect_size=effect, alpha=alpha, power=power, alternative="two-sided"
        )
    elif metric_type == "count":
        # 포아송 rate 비교, 정규 근사
        lam1, lam2 = baseline, baseline + mde
        z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
        per_group_base = (z ** 2) * (lam1 + lam2) / ((lam2 - lam1) ** 2)
    else:  # pragma: no cover - Literal 로 제한됨
        raise ValueError(f"unknown metric_type: {metric_type}")

    design_effect = 1.0
    if icc is not None and icc > 0:
        design_effect = 1 + (cluster_size - 1) * icc

    per_group = math.ceil(per_group_base * design_effect)
    return SamplePlanOutput(
        metric_type=metric_type,
        per_group=per_group,
        total=per_group * 2,
        design_effect=design_effect,
        assumptions={
            "baseline": baseline,
            "mde": mde,
            "alpha": alpha,
            "power": power,
            **({"std_dev": std_dev} if std_dev is not None else {}),
            **({"icc": icc} if icc is not None else {}),
        },
    )
