"""DesignAgent LLM 지표검토 — Goodhart/FWER/proxy/guardrail 정성 코멘트.

원칙(assembler 와 동일):
- **수치 불변**: LLM 은 표본수·MDE 등 숫자를 새로 만들지 않는다. 지표 *구성*의 위험만 정성 지적.
- **차단 없음**: 결과는 advisory. 실패 시 빈 MetricReview 폴백(파이프라인 보호).
- **모델**: 판정(judge=Haiku 고정)과 달리 추론이 필요한 비평 → 호출자가 고른 모델 사용.
  설계서 재현성을 위해 temperature=0.
"""
from __future__ import annotations

from typing import Callable, Optional

from src.design_schemas import HypothesisOutput, MetricReview
from src.llm_client import LLMProvider

# ── i18n 프롬프트 ────────────────────────────────────────────────────────────
# 통계 철학: p값(이분법적 유의성)보다 **효과크기·실질적 유의성·신뢰구간**을 중심에 둔다.
# 다중검정 위양성(FWER)은 실재하나, 조정의 무게중심은 "p값을 깎기"가 아니라
# "합의 MDE 대비 효과크기를 추정하기"에 둔다(추정 사고 > 이분법적 검정).
_SYSTEM = {
    "ko": "너는 A/B 실험 설계 검토자다. 지표 *구성*의 위험만 정성적으로 지적한다. "
          "통계 판단은 p값(이분법적 유의성)보다 **효과크기·실질적 유의성(합의 MDE 대비 크기)·"
          "신뢰구간**을 중심에 둔다. 표본수·p값 같은 구체 숫자를 새로 만들지 마라. 차단이 아니라 권고다.",
    "en": "You are an A/B experiment design reviewer. Critique only the *composition* of "
          "metrics, qualitatively. Center statistical judgment on **effect size, practical "
          "significance (magnitude vs the agreed MDE), and confidence intervals** rather than "
          "p-values (binary significance). Never invent concrete numbers (sample size, p-values). "
          "This is advisory, not blocking.",
}

_PROMPT = {
    "ko": """다음 실험의 지표 구성을 검토해 위험을 지적하라.

- 1차 지표(primary): {primary}
- 2차 지표(secondary, {n_secondary}개): {secondary}
- 부작용 감시 지표(tradeoff/guardrail, {n_tradeoff}개): {tradeoff}
- 지표 타입: {metric_type}

판단 원칙: **효과크기 중심**. p<0.05 여부보다 "효과크기가 합의 MDE(실질적으로 의미 있는
최소 크기)를 넘는가, 신뢰구간이 그 경계를 포함/배제하는가"로 평가하라.

다음 관점으로 각 위험을 risks 배열에 담아라(kind 값 사용):
- "effect_size": 설계가 효과크기·실질적 유의성보다 통계적 유의성(p값)에 치우칠 위험.
  예: 표본이 크면 MDE 미만의 사소한 효과도 p<0.05가 됨 → 1차 지표에 "실질적으로 의미 있는
  최소 효과크기(=합의 MDE)"를 명시하고 결과를 효과크기+신뢰구간으로 보고하도록 권고.
- "fwer": 2차 지표가 여러 개({n_secondary}개)면 다중검정으로 위양성이 늘 수 있음. 단,
  무게중심은 p값 보정이 아니라 **추정**에 둔다 — 1차 지표 단일 사전등록 + 효과크기 타깃을
  우선하고, 2차 지표는 탐색적으로(효과크기+신뢰구간 보고) 다뤄라. 보정(BH 등)은 보조.
- "goodhart": 1차/2차 지표가 대리지표로 게이밍되어 진짜 목표와 어긋날 위험
  (예: 클릭률만 올리고 전환·체류는 악화).
- "proxy": 1차 지표가 비즈니스 진짜 목표의 약한 대리지표인 경우.
- "guardrail": 부작용을 잡을 guardrail/tradeoff 지표가 비어있거나 부족한 경우.

각 risk 는 metric(대상 지표명, 전반이면 "(전체)"), kind, severity(low/medium/high),
note(위험 설명 + 구체적 완화 권고)를 채워라. 위험이 없으면 risks 는 빈 배열.
summary 에 1~2문장 총평을 한국어로 써라. 숫자를 새로 만들지 마라.""",
    "en": """Review this experiment's metric composition and flag risks.

- Primary: {primary}
- Secondary ({n_secondary}): {secondary}
- Tradeoff/guardrail ({n_tradeoff}): {tradeoff}
- Metric type: {metric_type}

Guiding principle: **effect-size-centered**. Judge by "does the effect size exceed the
agreed MDE (the minimum practically meaningful magnitude), and does the confidence interval
include/exclude that threshold" rather than whether p < 0.05.

Put each risk in the risks array using these kind values:
- "effect_size": the design over-indexes on statistical significance (p-values) instead of
  effect size / practical significance. E.g. with a large sample a trivial effect below the
  MDE still hits p<0.05 → recommend stating a "minimum practically meaningful effect size
  (= agreed MDE)" for the primary metric and reporting results as effect size + CI.
- "fwer": several secondary metrics ({n_secondary}) can inflate false positives under
  multiple comparisons. But center the fix on **estimation**, not p-value correction —
  prefer a single pre-registered primary with an effect-size target, and treat secondary
  metrics as exploratory (report effect sizes + CIs). Correction (BH, etc.) is secondary.
- "goodhart": primary/secondary metric gameable as a proxy, diverging from the true goal
  (e.g. lifting CTR while hurting conversion/retention).
- "proxy": the primary metric is a weak proxy for the real business goal.
- "guardrail": missing or insufficient guardrail/tradeoff metrics to catch side effects.

Each risk: metric (target name, "(전체)" if overall), kind, severity (low/medium/high),
note (risk + concrete mitigation). If none, risks is empty. Write a 1-2 sentence
summary. Never invent numbers.""",
}


def _lang(lang: str) -> str:
    return lang if lang in ("ko", "en") else "en"


def review_metrics(
    hyp: HypothesisOutput,
    *,
    metric_type: str,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: Optional[str] = None,
    _call: Optional[Callable] = None,
) -> MetricReview:
    """지표 구성 LLM 검토. _call 주입 시 테스트 mock. 실패 시 빈 MetricReview 폴백."""
    lg = _lang(lang)
    secondary = hyp.suggested_secondary_metrics
    tradeoff = hyp.predicted_tradeoff_metrics
    prompt = _PROMPT[lg].format(
        primary=hyp.suggested_primary_metric or "—",
        secondary="; ".join(secondary) or "—",
        n_secondary=len(secondary),
        tradeoff="; ".join(tradeoff) or "—",
        n_tradeoff=len(tradeoff),
        metric_type=metric_type,
    )
    if _call is None:
        from src.llm_json import call_structured
        _call = call_structured
    try:
        return _call(prompt=prompt, system=_SYSTEM[lg], schema=MetricReview,
                     api_key=api_key, provider=provider, lang=lg, model=model,
                     temperature=0.0)   # 설계서 재현성 (advisory 텍스트 안정화)
    except Exception as e:   # API 오류·검증 실패 → advisory 비차단, 빈 리뷰 폴백
        import logging
        logging.getLogger(__name__).warning("지표검토 LLM 실패 → 빈 리뷰 폴백: %s", e)
        return MetricReview()
