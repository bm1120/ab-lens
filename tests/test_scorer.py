"""tests/test_scorer.py — Scorer 단위 테스트.

결정론적 사전 필터 + LLM 평가(mocked) + get_weak_axes 검증.

실제 scorer.py 인터페이스:
  score_hypothesis(hypothesis, service_context, api_key, provider, lang, model)
  get_weak_axes(score, threshold=70) → 개별 임계값: clarity<60, mechanism<70,
                                        measurability<70, bias_risk<60
"""
from unittest.mock import patch

from src.design_schemas import HypothesisOutput, QualityScore, ServiceContext, RejectedAlternative
from src.hypothesis.scorer import score_hypothesis, get_weak_axes
from src.schemas import LLMProvider


# ── 공통 픽스처 ───────────────────────────────────────────────────────────────

def _hypothesis(mechanism_path: str = "버튼 이동 → 시야 진입 → 클릭 → 전환", measurability: bool = True):
    return HypothesisOutput(
        raw_idea="결제 전환율을 올리고 싶다",
        jtbd_reframe="사용자가 결제를 더 빨리 끝내도록",
        implicit_assumptions=["버튼 위치가 병목이다"],
        mechanism_path=mechanism_path,
        confounder_candidates=["요일 효과"],
        measurability_confirmed=measurability,
        sharpened_hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        suggested_primary_metric="checkout_conversion",
        suggested_secondary_metrics=["add_to_cart"],
        predicted_tradeoff_metrics=["page_load_time"],
        experiment_feasible=True,
    )


def _quality_score(clarity=80, mechanism=80, measurability=80, bias_risk=80) -> QualityScore:
    """LLM mock 에서 반환할 QualityScore 생성 헬퍼."""
    total = int(clarity * 0.2 + mechanism * 0.3 + measurability * 0.3 + bias_risk * 0.2)
    return QualityScore(
        clarity=clarity,
        mechanism=mechanism,
        measurability=measurability,
        bias_risk=bias_risk,
        total=total,
        weak_axes=[],
        passed=total >= 70,
        rationale="테스트용 품질 점수",
    )


# ── Task G1: Test 1 — mechanism=0 when mechanism_path is empty ──────────────

def test_scorer_mechanism_empty_returns_zero():
    """결정론적 사전 필터: mechanism_path 가 빈 문자열이면 mechanism=0 강제."""
    hyp = _hypothesis(mechanism_path="")
    # LLM 은 85 를 줄 것이지만 사전 필터로 덮어써야 함
    fake_score = _quality_score(mechanism=85)

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    assert result.mechanism == 0


def test_scorer_mechanism_short_returns_zero():
    """결정론적 사전 필터: mechanism_path 가 20자 미만이면 mechanism=0 강제."""
    hyp = _hypothesis(mechanism_path="짧은경로")  # 20자 미만
    fake_score = _quality_score(mechanism=75)

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    assert result.mechanism == 0


# ── Task G1: Test 2 — measurability=0 when measurability_confirmed=False ────

def test_scorer_measurability_false_returns_zero():
    """결정론적 사전 필터: measurability_confirmed=False 면 measurability=0 강제."""
    hyp = _hypothesis(measurability=False)
    fake_score = _quality_score(measurability=90)  # LLM 결과는 무시됨

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    assert result.measurability == 0


# ── Task G1: Test 3 — passed=True when total >= 70 ──────────────────────────

def test_scorer_passed_when_total_ge_70():
    """총점 70 이상이면 passed=True."""
    hyp = _hypothesis()
    # total = 80*0.2 + 80*0.3 + 80*0.3 + 80*0.2 = 80
    fake_score = _quality_score(clarity=80, mechanism=80, measurability=80, bias_risk=80)

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    assert result.total >= 70
    assert result.passed is True


# ── Task G1: Test 4 — passed=False when total < 70 ──────────────────────────

def test_scorer_failed_when_total_lt_70():
    """총점 70 미만이면 passed=False — 사전 필터로 mechanism=0 강제되는 케이스."""
    # mechanism_path 가 비어있으면 mechanism=0 강제
    # total = 80*0.2 + 0*0.3 + 80*0.3 + 80*0.2 = 16 + 0 + 24 + 16 = 56
    hyp = _hypothesis(mechanism_path="")
    fake_score = _quality_score(clarity=80, mechanism=85, measurability=80, bias_risk=80)

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    assert result.total < 70
    assert result.passed is False


# ── Task G1: Test 5 — get_weak_axes returns correct axes ────────────────────

def test_get_weak_axes_returns_below_threshold():
    """get_weak_axes: 개별 임계값 미달 축(mechanism<70, measurability<70) 반환."""
    score = QualityScore(
        clarity=75,
        mechanism=40,       # < 70 → weak
        measurability=55,   # < 70 → weak
        bias_risk=80,       # >= 60 → not weak
        total=56,
        weak_axes=[],
        passed=False,
        rationale="테스트",
    )
    weak = get_weak_axes(score)
    assert "mechanism" in weak
    assert "measurability" in weak
    assert "clarity" not in weak
    assert "bias_risk" not in weak


def test_get_weak_axes_clarity_threshold_is_60():
    """clarity 임계값은 60 (mechanism/measurability 와 다름)."""
    score = QualityScore(
        clarity=55,   # < 60 → weak
        mechanism=75,
        measurability=75,
        bias_risk=65,
        total=67,
        weak_axes=[],
        passed=False,
        rationale="테스트",
    )
    weak = get_weak_axes(score)
    assert "clarity" in weak
    assert "mechanism" not in weak
    assert "measurability" not in weak


def test_get_weak_axes_empty_when_all_pass():
    """모든 축이 각 임계값 이상이면 빈 리스트 반환."""
    score = QualityScore(
        clarity=70,
        mechanism=70,
        measurability=70,
        bias_risk=70,
        total=70,
        weak_axes=[],
        passed=True,
        rationale="통과",
    )
    assert get_weak_axes(score) == []


# ── Task G1: Test 6 — service_context=None still works (generic mode) ────────

def test_scorer_no_service_context():
    """service_context=None 이면 generic 모드로 정상 동작해야 한다."""
    hyp = _hypothesis()
    fake_score = _quality_score()

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score) as mock_cs:
        result = score_hypothesis(
            hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC
        )

    assert isinstance(result, QualityScore)
    assert mock_cs.call_count == 1


def test_scorer_with_service_context_includes_context_in_system():
    """service_context 가 있으면 system 프롬프트에 컨텍스트가 포함된다."""
    hyp = _hypothesis()
    fake_score = _quality_score()
    ctx = ServiceContext(
        service_name="MyShop",
        target_users="모바일 사용자",
        primary_metric="checkout_conversion",
        current_baseline="10%",
        past_experiments="3회 진행",
        domain_constraints="규제 없음",
    )

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score) as mock_cs:
        score_hypothesis(hyp, ctx, api_key="k", provider=LLMProvider.ANTHROPIC)

    # service_context 가 system 프롬프트에 포함되는지 확인
    system_arg = mock_cs.call_args.kwargs.get("system") or mock_cs.call_args.args[1]
    assert "MyShop" in system_arg


# ── 총점 재계산 정합성 ────────────────────────────────────────────────────────

def test_scorer_total_recalculated_after_filter():
    """사전 필터 적용 후 총점이 올바르게 재계산되는지 확인."""
    # measurability_confirmed=False → measurability=0 강제
    # clarity=80, mechanism=70, measurability(forced)=0, bias_risk=80
    # total = 80*0.2 + 70*0.3 + 0*0.3 + 80*0.2 = 16 + 21 + 0 + 16 = 53
    hyp = _hypothesis(measurability=False)
    fake_score = _quality_score(clarity=80, mechanism=70, measurability=90, bias_risk=80)

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    expected_total = int(80 * 0.2 + 70 * 0.3 + 0 * 0.3 + 80 * 0.2)
    assert result.total == expected_total
    assert result.measurability == 0


def test_scorer_returns_quality_score_type():
    """score_hypothesis 반환값이 QualityScore 인스턴스인지 확인."""
    hyp = _hypothesis()
    fake_score = _quality_score()

    with patch("src.hypothesis.scorer.call_structured", return_value=fake_score):
        result = score_hypothesis(hyp, None, api_key="k", provider=LLMProvider.ANTHROPIC)

    assert isinstance(result, QualityScore)
    assert hasattr(result, "clarity")
    assert hasattr(result, "mechanism")
    assert hasattr(result, "measurability")
    assert hasattr(result, "bias_risk")
    assert hasattr(result, "total")
    assert hasattr(result, "passed")
