"""골든셋 시나리오 8종 + 불변속성 check 함수.

각 check(api_key) -> bool: 실LLM(Claude Code Haiku)로 실행 후 '항상 참이어야 하는 속성' 검증.
점수 숫자가 아니라 구조적 불변속성을 본다 (비결정성에 강건).
spec: docs/design/golden-set-regression.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.hypothesis.bias_screener import screen_bias
from src.hypothesis.classify import classify_construct
from src.hypothesis.measurement import propose_measurement
from src.hypothesis.pipeline import run_hypothesis_pipeline
from src.hypothesis.quality_scorecard import judge_hypothesis, score_hypothesis
from src.hypothesis.trivial_router import route_trivial
from src.schemas import LLMProvider

PROVIDER = LLMProvider.CLAUDE_CODE  # 모델은 None → provider 기본 Haiku (재현성·비용 0)


@dataclass
class GoldenScenario:
    id: str
    label: str
    check: Callable[[str], bool]


def _pipeline(idea: str, key: str, *, mode: str = "quick", state: str = "initial_idea"):
    return run_hypothesis_pipeline(
        idea, mode=mode, hypothesis_state=state,
        api_key=key, provider=PROVIDER, lang="ko",
    )


def _gate_passed(h, key: str) -> bool:
    judgment = judge_hypothesis(h, api_key=key, provider=PROVIDER)  # Haiku temp=0
    return score_hypothesis(h, judgment).gate_passed


# ── 1. trivial → Just Do It ──────────────────────────────────────────────
def _check_trivial(key: str) -> bool:
    v = route_trivial("결제 버튼 라벨의 오타를 수정한다", api_key=key, provider=PROVIDER)
    return v.is_trivial is True


# ── 2. 명확 가설 → 게이트 통과 ────────────────────────────────────────────
def _check_clear(key: str) -> bool:
    r = _pipeline("결제 버튼을 결제 페이지 상단으로 옮기면 체크아웃 전환율이 오른다", key)
    return (not r.trivial) and r.hypothesis is not None and _gate_passed(r.hypothesis, key)


# ── 3. 모호 → 고도화 후 측정지표 + 메커니즘 명시 ──────────────────────────
def _check_vague(key: str) -> bool:
    r = _pipeline("클릭률을 올리고 싶다", key)
    if r.trivial or r.hypothesis is None:
        return False
    h = r.hypothesis
    return bool(h.suggested_primary_metric.strip()) and "→" in h.mechanism_path


# ── 4. anchored → anchoring 편향 active (deep 7종) ────────────────────────
def _check_anchored(key: str) -> bool:
    text = "경쟁사가 가격을 5% 올렸으니 우리도 정확히 5% 올리면 매출이 유지될 것이다"
    res = screen_bias(text, mode="deep", api_key=key, provider=PROVIDER)
    return any(b.bias_type == "anchoring" and b.status == "active" for b in res.biases)


# ── 5. 추상 목표 → 측정가능 프록시 지표로 구체화 ─────────────────────────
#   sharpener는 측정 가능성을 강제하므로 거의 모든 입력을 feasible로 만든다.
#   따라서 회귀로 보호할 가치 있는 불변속성은 "추상 목표를 줘도 측정가능 프록시
#   지표 + 명시 메커니즘으로 구체화한다"는 sharpener의 핵심 강점이다.
def _check_abstract_to_proxy(key: str) -> bool:
    r = _pipeline("브랜드 인지도를 높이면 장기적으로 전체 매출이 늘어날 것이다", key)
    if r.trivial or r.hypothesis is None:
        return False
    h = r.hypothesis
    return bool(h.suggested_primary_metric.strip()) and "→" in h.mechanism_path


# ── 6. 팀합의 → expander 스킵, 게이트 통과 ───────────────────────────────
def _check_team_agreed(key: str) -> bool:
    r = _pipeline("결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다", key, state="team_agreed")
    return (not r.trivial) and r.hypothesis is not None and _gate_passed(r.hypothesis, key)


# ── 7. 도메인: 이커머스 ──────────────────────────────────────────────────
def _check_ecommerce(key: str) -> bool:
    r = _pipeline("장바구니 결제 단계를 3단계에서 1단계로 줄이면 구매 전환율이 오른다", key)
    return (not r.trivial) and r.hypothesis is not None and _gate_passed(r.hypothesis, key)


# ── 8. 도메인: SaaS ──────────────────────────────────────────────────────
def _check_saas(key: str) -> bool:
    r = _pipeline("신규 가입자에게 온보딩 체크리스트를 제공하면 7일 내 활성화율이 오른다", key)
    return (not r.trivial) and r.hypothesis is not None and _gate_passed(r.hypothesis, key)


# ── 9~11. 개념→조작 정의화 (P1/P4) ──────────────────────────────────────
def _check_classify_clear(key: str) -> bool:
    c = classify_construct("결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
                           api_key=key, provider=PROVIDER)
    return c.kind == "clear"


def _check_classify_abstract(key: str) -> bool:
    c = classify_construct("브랜드 인지도를 높이면 장기적으로 전체 매출이 늘어날 것이다",
                           api_key=key, provider=PROVIDER)
    return c.kind in ("abstract", "mixed") and len(c.constructs) >= 1


def _check_measurement_compatible(key: str) -> bool:
    # 추상 개념 → 개념정의 + 탭2 호환(ab_testable) 지표 후보 ≥1
    m = propose_measurement("브랜드 인지도를 높이면 장기 매출이 는다", ["브랜드 인지도"],
                            "이커머스 웹사이트", api_key=key, provider=PROVIDER)
    if not m.measurements:
        return False
    cm = m.measurements[0]
    has_compat = any(c.ab_testable and c.metric_type in ("proportion", "continuous", "count")
                     for c in cm.candidates)
    return bool(cm.conceptual_definition.strip()) and has_compat


SCENARIOS: list[GoldenScenario] = [
    GoldenScenario("trivial", "trivial → Just Do It", _check_trivial),
    GoldenScenario("clear", "명확 가설 → 게이트 통과", _check_clear),
    GoldenScenario("vague", "모호 → 측정지표+메커니즘", _check_vague),
    GoldenScenario("anchored", "anchored → anchoring active", _check_anchored),
    GoldenScenario("abstract_proxy", "추상 목표 → 측정가능 프록시", _check_abstract_to_proxy),
    GoldenScenario("team_agreed", "팀합의 → 게이트 통과", _check_team_agreed),
    GoldenScenario("ecommerce", "도메인:이커머스 → 게이트 통과", _check_ecommerce),
    GoldenScenario("saas", "도메인:SaaS → 게이트 통과", _check_saas),
    GoldenScenario("classify_clear", "명확 입력 → clear 분류", _check_classify_clear),
    GoldenScenario("classify_abstract", "추상 입력 → abstract/mixed + 구성개념", _check_classify_abstract),
    GoldenScenario("measurement_compatible", "추상 → 개념정의+탭2호환 지표 후보", _check_measurement_compatible),
]
