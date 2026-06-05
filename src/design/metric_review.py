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
_SYSTEM = {
    "ko": "너는 A/B 실험 설계 검토자다. 지표 *구성*의 위험만 정성적으로 지적한다. "
          "표본수·p값·효과크기 같은 숫자를 새로 만들지 마라. 차단이 아니라 권고다.",
    "en": "You are an A/B experiment design reviewer. Critique only the *composition* of "
          "metrics, qualitatively. Never invent numbers (sample size, p-values, effect size). "
          "This is advisory, not blocking.",
}

_PROMPT = {
    "ko": """다음 실험의 지표 구성을 검토해 위험을 지적하라.

- 1차 지표(primary): {primary}
- 2차 지표(secondary, {n_secondary}개): {secondary}
- 부작용 감시 지표(tradeoff/guardrail, {n_tradeoff}개): {tradeoff}
- 지표 타입: {metric_type}

다음 관점으로 각 위험을 risks 배열에 담아라(kind 값 사용):
- "goodhart": 1차/2차 지표가 대리지표로 게이밍되어 진짜 목표와 어긋날 위험
  (예: 클릭률만 올리고 전환·체류는 악화).
- "fwer": 2차 지표가 여러 개({n_secondary}개)면 다중검정으로 위양성(1종 오류)이 팽창.
  Bonferroni/Benjamini-Hochberg 같은 보정 또는 1차 지표 단일 검정 우선을 권고.
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

Put each risk in the risks array using these kind values:
- "goodhart": primary/secondary metric gameable as a proxy, diverging from the true goal
  (e.g. lifting CTR while hurting conversion/retention).
- "fwer": with several secondary metrics ({n_secondary}), multiple comparisons inflate
  false positives. Recommend Bonferroni/Benjamini-Hochberg correction or a single
  pre-registered primary test.
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
