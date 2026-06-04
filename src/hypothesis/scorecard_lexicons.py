"""HQS 룰 차원 + LLM judge 프롬프트의 lang별 렉시콘 (i18n).

PR #4 🔴 Blocker(한국어 하드코딩) + cross_verify 지적(소문자/활용형/복합어/프롬프트 i18n) 반영.
미지원 lang은 **en으로 폴백**(LLM 평가 컨텍스트상 더 안전 — 한국어 룰을 강요하지 않음).
"""
from __future__ import annotations

import re

# 동어반복 지표 화이트리스트 — primary_metric이 가설 어휘를 복붙 (D1)
VAGUE_METRIC = {
    "ko": {"성공", "성공률", "개선", "향상", "효과", "지표", "결과", "퍼포먼스", "성과"},
    "en": {"success", "improvement", "effect", "metric", "result", "performance",
           "kpi", "outcome", "engagement", "satisfaction"},
}

# 구체성 모호어 — D6 게이밍 차단 (substring 매칭 — 복합어 포함)
VAGUE_TERMS = {
    "ko": {"등", "관련", "전반", "다양한", "여러", "적절히", "최적화", "더 나은",
           "어느 정도", "개선", "향상", "좋아", "나아"},
    "en": {"etc", "various", "overall", "appropriately", "optimiz", "better",
           "somewhat", "improv", "enhanc", "relevant", "general", "leverage", "robust"},
}

# 방향어휘 — D2 룰 (반증 가능한 방향성 주장). 활용형(-e/-es/-ed/-ing) 포함.
_DIRECTION_SRC = {
    "ko": r"(증가|감소|상승|하락|높|낮|늘|줄|개선|악화|차이|많아|적어|길어|짧아|향상|떨어)",
    "en": r"\b(increas|decreas|ris|drop|rais|higher|lower|more|fewer|less|"
          r"reduc|improv|worsen|differ|longer|shorter|grow|boost)(e|es|ed|ing)?\b",
}

# ── LLM judge 프롬프트 (lang별) ─────────────────────────────
JUDGE_SYSTEM = {
    "ko": ("너는 가설 품질 판정자다. **점수(숫자) 생성 금지.** 각 항목의 판정 규칙을 그대로 적용해 "
           "Y/P/N(또는 Y/N)과 1줄 근거만 낸다. 규칙 밖 임의 판단 금지."),
    "en": ("You are a hypothesis quality judge. **Never produce numeric scores.** Apply each item's "
           "decision rule exactly and output only Y/P/N (or Y/N) plus a one-line rationale. No free judgment."),
}

JUDGE_PROMPT = {
    "ko": """다음 가설을 항목별 **판정 규칙**대로만 판정하라.

[falsifiable] (Y/N) — '이 가설이 틀렸다'고 판명날 **구체적 관측 시나리오를 1문장으로 쓸 수 있을 때만 Y**.
  방향 없는 동어반복("품질이 좋아진다")이면 N. Y면 falsify_scenario에 그 1문장.
[mechanism_plausible] (Y/P/N) — 개입→행동→지표의 **각 링크마다 (원인 명시) (효과 명시)** 를 확인.
  Y=모든 링크 인과·비약없음 / P=정확히 한 링크가 미진술 가정 필요 / N=링크 누락 또는 상관을 인과로 둔갑. mechanism_gap에 끊긴 링크.
[clarity] (Y/P/N) — Y=단일개입+단일1차지표+방향명시+해석유일 / P=모호요소 1개 / N=다의·복합. clarity_issue에 사유.
[confound_relevant] (Y/P/N) — 나열된 교란후보가 **처치 배정 AND 지표 둘 다에 실질 영향**을 주는 핵심 변수인가(개수 무관, 타당성만).
  Y=핵심 교란이 실질 영향 / P=영향이 미미·간접 / N=일반론·무관.
[tradeoff_real] (Y/P/N) — 1차지표 개선 시 **실제 악화될 가드레일**이 있으면 Y / 약하면 P / 무관·없음 N.
[alt_justified] (Y/P/N) — rejected에 '왜 이 가설이 나은지' **실질 사유**: Y=실질사유 / P=빈약 / N=없음.
risk_issue·alt_issue에 1줄 근거.

가설: {sharpened_hypothesis}
메커니즘: {mechanism_path}
JTBD: {jtbd_reframe}
1차지표: {primary_metric}
보조지표: {secondary}
트레이드오프: {tradeoffs}
교란후보: {confounders}
기각대안: {rejected}
""",
    "en": """Judge the hypothesis by each item's **decision rule** only.

[falsifiable] (Y/N) — Y only if you can write a **concrete observation in one sentence that would prove it FALSE**.
  Directionless tautology ("quality improves") = N. If Y, put that sentence in falsify_scenario.
[mechanism_plausible] (Y/P/N) — For each link in intervention→behavior→metric, check (cause stated)(effect stated).
  Y=all links causal, no leap / P=exactly one link needs an unstated assumption / N=missing link or correlation-as-causation. Put the broken link in mechanism_gap.
[clarity] (Y/P/N) — Y=single intervention+single primary metric+explicit direction+one interpretation / P=one vague element / N=ambiguous/compound.
[confound_relevant] (Y/P/N) — Are listed confounders **key variables that plausibly affect BOTH treatment assignment AND the metric** (relevance only, ignore count)?
  Y=key confounder with real effect / P=minor/indirect / N=generic/irrelevant.
[tradeoff_real] (Y/P/N) — Y if a listed guardrail could **actually worsen when the primary improves** / P weak / N none.
[alt_justified] (Y/P/N) — substantive reason in rejected_alternatives: Y=substantive / P=thin / N=none.
Put one-line rationale in risk_issue / alt_issue.

Hypothesis: {sharpened_hypothesis}
Mechanism: {mechanism_path}
JTBD: {jtbd_reframe}
Primary metric: {primary_metric}
Secondary: {secondary}
Tradeoffs: {tradeoffs}
Confounders: {confounders}
Rejected: {rejected}
""",
}


def _lang(lang: str) -> str:
    return lang if lang in ("ko", "en") else "en"   # 미지원 → en 폴백


def vague_metric_set(lang: str) -> set[str]:
    return VAGUE_METRIC[_lang(lang)]


def vague_terms_set(lang: str) -> set[str]:
    return VAGUE_TERMS[_lang(lang)]


def direction_rx(lang: str) -> re.Pattern:
    flags = re.IGNORECASE if _lang(lang) == "en" else 0
    return re.compile(_DIRECTION_SRC[_lang(lang)], flags)


def judge_system(lang: str) -> str:
    return JUDGE_SYSTEM[_lang(lang)]


def judge_prompt_template(lang: str) -> str:
    return JUDGE_PROMPT[_lang(lang)]


def norm_token(t: str, lang: str) -> str:
    """비교용 정규화 — en은 소문자, 양끝 구두점 제거."""
    import string
    t = t.strip(string.punctuation + "“”‘’·")
    return t.lower() if _lang(lang) == "en" else t
