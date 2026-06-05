"""표준 실험 설계서 Markdown 생성 (deterministic 템플릿).

LLM 산문 생성이 아니라 DesignContext + HypothesisOutput 의 값을 인용해 채운다.
→ 수치를 새로 지어내지 않음(불변 원칙). .docx 변환은 Phase 2.
"""
from __future__ import annotations

from src.design_schemas import DesignContext, HypothesisOutput

_KIND_LABEL = {
    "effect_size": "효과크기 중심성",
    "goodhart": "Goodhart(지표 게이밍)",
    "fwer": "FWER(다중검정)",
    "proxy": "대리지표 괴리",
    "guardrail": "guardrail 누락",
}
_SEV_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def _render_metric_review(ctx: DesignContext) -> str:
    mr = ctx.metric_review
    if mr is None or not mr.risks:
        return ""
    lines = []
    for r in mr.risks:
        label = _KIND_LABEL.get(r.kind, r.kind)
        icon = _SEV_ICON.get(r.severity, "🟡")
        lines.append(f"- {icon} **[{label}] {r.metric}** — {r.note}")
    body = "\n".join(lines)
    summary = f"\n\n> {mr.summary}" if mr.summary else ""
    return f"""

## 지표 리스크 검토 (DesignAgent · advisory)
{body}{summary}"""


def render_design_doc(ctx: DesignContext, hyp: HypothesisOutput) -> str:
    secondary = ", ".join(hyp.suggested_secondary_metrics) or "—"
    tradeoff = ", ".join(hyp.predicted_tradeoff_metrics) or "—"
    confounders = "\n".join(f"- {c}" for c in hyp.confounder_candidates) or "- —"
    rejected = (
        "\n".join(f"- ~~{r.hypothesis}~~ — {r.rejection_reason}" for r in hyp.rejected_alternatives)
        or "- 없음"
    )
    std_dev = ctx.std_dev if ctx.std_dev is not None else "—"
    icc = ctx.icc if ctx.icc is not None else "—"

    return f"""# 실험 설계서: {ctx.sharpened_hypothesis}

## 가설
- **고도화된 가설**: {ctx.sharpened_hypothesis}
- **JTBD 재프레이밍**: {hyp.jtbd_reframe}
- **메커니즘**: {hyp.mechanism_path}

## 지표
- **1차 지표 (primary)**: {ctx.primary_metric}
- **2차 지표 (secondary)**: {secondary}
- **부작용 감시 지표 (tradeoff)**: {tradeoff}

## 통계 설계 (사용자 입력 사실수치 기반)
| 항목 | 값 |
|---|---|
| 지표 타입 | {ctx.metric_type} |
| baseline | {ctx.baseline} |
| 합의 MDE | {ctx.agreed_mde} |
| 표준편차 (std_dev) | {std_dev} |
| 유의수준 (alpha) | {ctx.alpha} |
| 검정력 (power) | {ctx.power} |
| **필요 표본 (총)** | **{ctx.target_sample_size:,}** |
| 실험 기간(일) | {ctx.experiment_duration_days} |
| 랜덤화 단위 | {ctx.randomization_unit} |
| ICC | {icc} |

## 혼란변수 후보
{confounders}

## 중단 기준 (peeking 방지)
{ctx.stop_criteria}

## 설계 시점 편향 스크리닝
{ctx.bias_screening_summary}

## 기각된 대안 (Decision Log)
{rejected}

## 설계 품질
- 필수 통과: {"✅" if ctx.design_quality.required_pass else "🔴"}
- 권고 점수: {ctx.design_quality.advisory_score}/100
{_render_metric_review(ctx)}

---
> 이 설계서와 함께 다운로드한 `ab-design-context.json` 을 결과 분석 탭에 업로드하면,
> 분석 시점에 이 약속(표본/지표/MDE)을 위반하는지 자동 검증합니다 (Context Loop).
"""
