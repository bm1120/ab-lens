"""실제 LLM 호출을 통한 프롬프트 품질 검증 테스트.

mock 없이 Claude Code OAuth 토큰으로 실제 LLM 을 호출하여:
- 출력 구조 유효성 (Pydantic 파싱 성공)
- 출력 품질 어서션 (JTBD 패턴, mechanism_path 화살표, BiasType enum, trivial 판정)
을 검증한다.

CLAUDE_CODE_OAUTH_TOKEN 이 없으면 전체 스킵된다.
"""
from __future__ import annotations

import re

import pytest

from src.bias_pool import BIAS_REFERENCE_POOL
from src.config import get_credential
from src.design_schemas import BiasScreenResult, HypothesisOutput
from src.hypothesis.bias_screener import screen_bias
from src.hypothesis.expander import ExpanderOutput, expand
from src.hypothesis.sharpener import sharpen
from src.hypothesis.trivial_router import TrivialVerdict, route_trivial
from src.schemas import LLMProvider

TOKEN = get_credential("CLAUDE_CODE_OAUTH_TOKEN")
PROVIDER = LLMProvider.CLAUDE_CODE
SKIP_NO_TOKEN = pytest.mark.skipif(not TOKEN, reason="CLAUDE_CODE_OAUTH_TOKEN 없음 — 스킵")

IDEA_KO = "버튼 색을 바꾸면 클릭률이 오를 것 같다"
VALID_BIAS_TYPES = set(BIAS_REFERENCE_POOL.keys())


def _get_token() -> str:
    assert TOKEN, "TOKEN is None"
    return TOKEN


# ──────────────────────────────────────────────────────────────
# 1. HypothesisExpander
# ──────────────────────────────────────────────────────────────

@SKIP_NO_TOKEN
def test_expander_structure():
    """expand() 가 ExpanderOutput 으로 파싱되는지 검증."""
    out = expand(IDEA_KO, api_key=_get_token(), provider=PROVIDER)
    assert isinstance(out, ExpanderOutput), "ExpanderOutput 파싱 실패"


@SKIP_NO_TOKEN
def test_expander_jtbd_reframe_pattern():
    """jtbd_reframe 이 JTBD 패턴을 포함하는지 확인."""
    out = expand(IDEA_KO, api_key=_get_token(), provider=PROVIDER)
    reframe = out.jtbd_reframe
    has_when = bool(re.search(r"When\b|언제|~할\s*때|할\s*때", reframe, re.IGNORECASE))
    has_want = bool(re.search(
        r"I\s+want|~하고\s*싶|하고\s*싶|원한다|원해|하길\s*원", reframe, re.IGNORECASE
    ))
    has_so_i_can = bool(re.search(
        r"so\s+I\s+can|~할\s*수\s*있도록|할\s*수\s*있도록|위해|수\s*있게", reframe, re.IGNORECASE
    ))
    matched = sum([has_when, has_want, has_so_i_can])
    assert matched >= 2, (
        f"jtbd_reframe JTBD 패턴 불충분 ({matched}/3):\n{reframe}"
    )


@SKIP_NO_TOKEN
def test_expander_min_candidates():
    out = expand(IDEA_KO, api_key=_get_token(), provider=PROVIDER)
    assert len(out.candidate_hypotheses) >= 3, f"후보 가설이 3개 미만: {out.candidate_hypotheses}"


@SKIP_NO_TOKEN
def test_expander_implicit_assumptions_nonempty():
    out = expand(IDEA_KO, api_key=_get_token(), provider=PROVIDER)
    assert len(out.implicit_assumptions) >= 1, "암묵적 전제가 비어 있음"


# ──────────────────────────────────────────────────────────────
# 2. HypothesisSharpener
# ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def expander_output():
    if not TOKEN:
        pytest.skip("CLAUDE_CODE_OAUTH_TOKEN 없음")
    return expand(IDEA_KO, api_key=_get_token(), provider=PROVIDER)


@SKIP_NO_TOKEN
def test_sharpener_structure(expander_output):
    out = sharpen(IDEA_KO, expander_output, api_key=_get_token(), provider=PROVIDER)
    assert isinstance(out, HypothesisOutput), "HypothesisOutput 파싱 실패"


@SKIP_NO_TOKEN
def test_sharpener_mechanism_path_arrow(expander_output):
    out = sharpen(IDEA_KO, expander_output, api_key=_get_token(), provider=PROVIDER)
    has_arrow = "→" in out.mechanism_path or "->" in out.mechanism_path
    assert has_arrow, f"mechanism_path 에 화살표(→) 없음: {out.mechanism_path!r}"


@SKIP_NO_TOKEN
def test_sharpener_confounder_candidates(expander_output):
    out = sharpen(IDEA_KO, expander_output, api_key=_get_token(), provider=PROVIDER)
    assert len(out.confounder_candidates) >= 1, "혼란변수(confounder_candidates)가 비어 있음"


@SKIP_NO_TOKEN
def test_sharpener_raw_idea_preserved(expander_output):
    out = sharpen(IDEA_KO, expander_output, api_key=_get_token(), provider=PROVIDER)
    assert out.raw_idea == IDEA_KO, f"raw_idea 불일치: {out.raw_idea!r} != {IDEA_KO!r}"


@SKIP_NO_TOKEN
def test_sharpener_measurability_confirmed(expander_output):
    out = sharpen(IDEA_KO, expander_output, api_key=_get_token(), provider=PROVIDER)
    assert isinstance(out.measurability_confirmed, bool)


# ──────────────────────────────────────────────────────────────
# 3. BiasScreener
# ──────────────────────────────────────────────────────────────

SHARPENED_HYPOTHESIS_TEXT = (
    "버튼 색을 파란색으로 변경하면 사용자의 시각적 주목도가 높아져 클릭률(CTR)이 증가할 것이다."
)


@SKIP_NO_TOKEN
def test_bias_screener_structure_quick():
    out = screen_bias(SHARPENED_HYPOTHESIS_TEXT, mode="quick", api_key=_get_token(), provider=PROVIDER)
    assert isinstance(out, BiasScreenResult)


@SKIP_NO_TOKEN
def test_bias_screener_bias_type_enum_quick():
    out = screen_bias(SHARPENED_HYPOTHESIS_TEXT, mode="quick", api_key=_get_token(), provider=PROVIDER)
    for item in out.biases:
        assert item.bias_type in VALID_BIAS_TYPES, f"풀 외 bias_type: {item.bias_type!r}"


@SKIP_NO_TOKEN
def test_bias_screener_bias_type_enum_deep():
    out = screen_bias(SHARPENED_HYPOTHESIS_TEXT, mode="deep", api_key=_get_token(), provider=PROVIDER)
    for item in out.biases:
        assert item.bias_type in VALID_BIAS_TYPES, f"풀 외 bias_type: {item.bias_type!r}"


@SKIP_NO_TOKEN
def test_bias_screener_status_values():
    allowed = {"active", "latent", "not_applicable"}
    out = screen_bias(SHARPENED_HYPOTHESIS_TEXT, mode="quick", api_key=_get_token(), provider=PROVIDER)
    for item in out.biases:
        assert item.status in allowed, f"허용 외 status: {item.status!r}"


@SKIP_NO_TOKEN
def test_bias_screener_evidence_and_counter_measure_nonempty():
    out = screen_bias(SHARPENED_HYPOTHESIS_TEXT, mode="quick", api_key=_get_token(), provider=PROVIDER)
    for item in out.biases:
        assert item.evidence.strip(), f"evidence 가 비어 있음: {item}"
        assert item.counter_measure.strip(), f"counter_measure 가 비어 있음: {item}"


@SKIP_NO_TOKEN
def test_bias_screener_warning_only():
    out = screen_bias(SHARPENED_HYPOTHESIS_TEXT, mode="quick", api_key=_get_token(), provider=PROVIDER)
    assert out.warning_only is True


# ──────────────────────────────────────────────────────────────
# 4. TrivialRouter
# ──────────────────────────────────────────────────────────────

@SKIP_NO_TOKEN
def test_trivial_router_typo_fix_is_trivial():
    """오타 수정 → is_trivial=True 기대."""
    out = route_trivial("로그인 버튼 오타 수정", api_key=_get_token(), provider=PROVIDER)
    assert isinstance(out, TrivialVerdict)
    assert out.is_trivial is True, f"오타 수정을 사소하지 않다고 판정: reason={out.reason!r}"


@SKIP_NO_TOKEN
def test_trivial_router_onboarding_is_not_trivial():
    """신규 유저 온보딩 단계 축소 → is_trivial=False 기대."""
    out = route_trivial("신규 유저 온보딩 단계 축소", api_key=_get_token(), provider=PROVIDER)
    assert isinstance(out, TrivialVerdict)
    assert out.is_trivial is False, f"온보딩 단계 축소를 사소하다고 판정: reason={out.reason!r}"


@SKIP_NO_TOKEN
def test_trivial_router_reason_nonempty():
    out = route_trivial("로그인 버튼 오타 수정", api_key=_get_token(), provider=PROVIDER)
    assert out.reason.strip(), "reason 이 비어 있음"
