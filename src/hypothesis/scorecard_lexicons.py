"""HQS 룰 차원용 lang별 렉시콘 (i18n).

기존 설계가 한국어 정규식/단어셋 하드코딩이라 영어 가설이 전부 게이트 결격되는
문제(PR #4 리뷰 🔴 Blocker)를 해소한다. `lang`별로 분리하고, 미지원 lang은 ko로 폴백.
"""
from __future__ import annotations

import re

# 동어반복 지표 화이트리스트 — primary_metric이 가설 어휘를 그대로 복붙한 경우 (D1)
VAGUE_METRIC = {
    "ko": {"성공", "성공률", "개선", "향상", "효과", "지표", "결과", "퍼포먼스", "성과"},
    "en": {"success", "improvement", "effect", "metric", "result", "performance", "kpi", "outcome"},
}

# 구체성 모호어 — D6 게이밍 차단 (밀도 채점)
VAGUE_TERMS = {
    "ko": {"등", "관련", "전반", "다양한", "여러", "적절히", "최적화", "더 나은", "어느 정도", "개선", "향상"},
    "en": {"etc", "various", "overall", "appropriately", "optimize", "better", "somewhat",
           "improve", "enhance", "relevant", "general"},
}

# 방향어휘 — D2 룰 파트 (반증 가능한 방향성 주장인지)
_DIRECTION_SRC = {
    "ko": r"(증가|감소|상승|하락|높|낮|늘|줄|개선되|악화|차이|많아|적어|길어|짧아)",
    "en": r"\b(increase|decrease|rise|drop|higher|lower|more|fewer|less|reduce|improve|worsen|differ|longer|shorter)\b",
}


def _lang(lang: str) -> str:
    return lang if lang in ("ko", "en") else "ko"


def vague_metric_set(lang: str) -> set[str]:
    return VAGUE_METRIC[_lang(lang)]


def vague_terms_set(lang: str) -> set[str]:
    return VAGUE_TERMS[_lang(lang)]


def direction_rx(lang: str) -> re.Pattern:
    flags = re.IGNORECASE if _lang(lang) == "en" else 0
    return re.compile(_DIRECTION_SRC[_lang(lang)], flags)
