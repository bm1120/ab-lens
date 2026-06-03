"""BiasScreener — 설계 시점 편향 스크리닝 (bias-check 이식).

블로킹하지 않고 Warning 만 단다(warning_only=True). Quick 모드는 가장 흔한 3종,
Deep 모드는 풀 7종 전체를 검토한다.
"""
from __future__ import annotations

from typing import Literal

from src.bias_pool import BIAS_REFERENCE_POOL
from src.design_schemas import BiasScreenResult
from src.llm_json import call_structured
from src.schemas import LLMProvider

# Quick 모드에서 다루는 3종 (가장 흔한 설계 편향)
QUICK_BIASES = ("confirmation_bias", "anchoring", "sunk_cost_fallacy")


def _system(mode: Literal["quick", "deep"], lang: str) -> str:
    if mode == "quick":
        targets = QUICK_BIASES
    else:
        targets = tuple(BIAS_REFERENCE_POOL.keys())
    pool_desc = "; ".join(f"{k}({BIAS_REFERENCE_POOL[k]['mechanism']})" for k in targets)
    if lang == "ko":
        return (
            "당신은 실험 설계 편향 스크리너입니다. 다음 편향만 검토하세요: "
            f"{pool_desc}. 각 편향에 대해 status(active/latent/not_applicable), evidence, "
            "counter_measure 를 제시하세요. 블로킹하지 말고 경고만 합니다. "
            "반드시 BiasScreenResult JSON 스키마로만 답하세요."
        )
    return (
        "You are an experiment-design bias screener. Review ONLY these biases: "
        f"{pool_desc}. For each, give status(active/latent/not_applicable), evidence, "
        "counter_measure. Warn only, never block. Answer ONLY as BiasScreenResult JSON."
    )


def screen_bias(
    hypothesis_text: str,
    mode: Literal["quick", "deep"],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> BiasScreenResult:
    out = call_structured(
        prompt=hypothesis_text,
        system=_system(mode, lang),
        schema=BiasScreenResult,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )
    biases = out.biases
    if mode == "quick":
        biases = [b for b in biases if b.bias_type in QUICK_BIASES]
    active_count = sum(1 for b in biases if b.status == "active")
    return BiasScreenResult(biases=biases, active_count=active_count, warning_only=True)
