"""탭2 end-to-end 통합 테스트 — Claude Code OAuth 실제 호출.

실행 방법:
    uv run pytest tests/test_tab2_e2e.py -v -s --no-header

5개 기본 시나리오 + 3개 Context Loop 시나리오 = 8개
"""
import pytest
from src.config import get_credential
from src.schemas import ABTestInput, LLMProvider
from src.agents.statistical import analyze_stats
from src.agents.bias_detector import detect_bias
from src.agents.recommender import recommend
from src.context_loop import build_observed_result, context_loop_guard
from src.design_schemas import DesignContext, DesignQuality

TOKEN = get_credential("CLAUDE_CODE_OAUTH_TOKEN")
PROVIDER = LLMProvider.CLAUDE_CODE

pytestmark = pytest.mark.skipif(
    not TOKEN,
    reason="CLAUDE_CODE_OAUTH_TOKEN 없음 — ~/.hermes/.env 확인",
)


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

_DEFAULT_DQ = DesignQuality(
    required_pass=True,
    required_items={"primary_metric_defined": True, "randomization_unit_clear": True},
    advisory_score=80,
    advisory_items={"hypothesis_sharpened": True, "stop_criteria_agreed": True},
)

_BASE_CTX = DesignContext(
    sharpened_hypothesis="CTA 버튼 색상 변경 → 신규 유저 전환율 +3pp",
    primary_metric="전환율",
    metric_type="proportion",
    agreed_mde=0.03,
    baseline=0.050,
    std_dev=None,
    alpha=0.05,
    power=0.8,
    target_sample_size=10000,
    experiment_duration_days=14,
    randomization_unit="user",
    icc=None,
    stop_criteria="14일 또는 n=10000 달성 시",
    design_quality=_DEFAULT_DQ,
    bias_screening_summary="Anchoring 경고 — 첫 아이디어(색상)에 고착 가능성",
    alternative_selected=None,
)


def _make_design_ctx(**overrides) -> DesignContext:
    """테스트용 DesignContext — 기본값에서 일부 필드만 오버라이드."""
    return _BASE_CTX.model_copy(update=overrides)


def run_tab2_pipeline(inp: ABTestInput, design_ctx: DesignContext | None = None):
    """통계분석 → Context Loop → 편향감지 → 추천."""
    stats = analyze_stats(inp)

    violations = []
    if design_ctx:
        observed = build_observed_result(inp, stats)
        violations = context_loop_guard(design_ctx, observed)

    bias = detect_bias(inp, stats, api_key=TOKEN, provider=PROVIDER)
    rec = recommend(inp, stats, bias, api_key=TOKEN, provider=PROVIDER)

    return stats, violations, bias, rec


# ── 시나리오 1: clear_win ─────────────────────────────────────────────────────

def test_clear_win():
    """유의한 양의 효과 → 출시 권고 기대."""
    inp = ABTestInput(
        metric_name="전환율",
        treatment_value=0.065,
        control_value=0.050,
        p_value=0.012,
        sample_size_treatment=5000,
        sample_size_control=5000,
        experiment_days=14,
        is_random_assignment=True,
        multiple_metrics=False,
        business_context="신규 CTA 버튼 색상 변경 실험",
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp)

    print(f"\n[clear_win] effect={stats.effect_size_pp:+.2f}pp, "
          f"power={stats.power_pct:.0f}%, SRM={stats.srm_detected}")
    print(f"  bias.overall_risk={bias.overall_risk}")
    print(f"  final_recommendation={rec.final_recommendation[:80]}")
    print(f"  confidence_pct={rec.confidence_pct}")

    assert stats.is_significant
    assert stats.effect_size_pp > 0
    assert not stats.srm_detected
    assert violations == []
    # 출시 권고 키워드 포함 여부 (final_recommendation 자유 텍스트)
    rec_lower = rec.final_recommendation.lower()
    assert any(kw in rec_lower for kw in ["출시", "배포", "launch", "deploy", "proceed", "ship"])
    assert rec.confidence_pct >= 60


# ── 시나리오 2: clear_loss ────────────────────────────────────────────────────

def test_clear_loss():
    """유의한 음의 효과 → 롤백/중단 권고."""
    inp = ABTestInput(
        metric_name="전환율",
        treatment_value=0.038,
        control_value=0.050,
        p_value=0.003,
        sample_size_treatment=5000,
        sample_size_control=5000,
        experiment_days=14,
        is_random_assignment=True,
        multiple_metrics=False,
        business_context="결제 플로우 간소화 실험",
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp)

    print(f"\n[clear_loss] effect={stats.effect_size_pp:+.2f}pp, "
          f"final_recommendation={rec.final_recommendation[:80]}")

    assert stats.is_significant
    assert stats.effect_size_pp < 0
    rec_lower = rec.final_recommendation.lower()
    # 음의 효과 → 중단/롤백/추가실험/조건부 등 '신중 행동'을 권고해야 함.
    # (출시 키워드 블록리스트는 "전면 출시를 권하지 않음" 같은 부정문을 오탐 → 긍정 신호로 검증)
    caution_kw = ["추가 실험", "추가실험", "중단", "롤백", "보류", "조건부", "재실험", "되돌", "권장하지",
                  "further", "rollback", "hold", "do not", "not launch", "conditional", "discontinue"]
    assert any(kw in rec_lower for kw in caution_kw), rec.final_recommendation


# ── 시나리오 3: inconclusive ──────────────────────────────────────────────────

def test_inconclusive():
    """비유의, 낮은 검정력 → 추가 실험 또는 중립 권고."""
    inp = ABTestInput(
        metric_name="클릭률",
        treatment_value=0.052,
        control_value=0.050,
        p_value=0.38,
        sample_size_treatment=1200,
        sample_size_control=1200,
        experiment_days=7,
        is_random_assignment=True,
        multiple_metrics=False,
        business_context="검색창 위치 변경 소규모 실험",
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp)

    print(f"\n[inconclusive] power={stats.power_pct:.0f}%, "
          f"final_recommendation={rec.final_recommendation[:80]}")

    assert not stats.is_significant
    assert stats.power_pct < 80
    # 출시 추천 아님
    rec_lower = rec.final_recommendation.lower()
    assert not any(kw in rec_lower for kw in ["즉시 출시", "immediate launch"])


# ── 시나리오 4: srm_detected ──────────────────────────────────────────────────

def test_srm_detected():
    """Sample Ratio Mismatch → srm_detected=True."""
    inp = ABTestInput(
        metric_name="구매율",
        treatment_value=0.062,
        control_value=0.050,
        p_value=0.021,
        sample_size_treatment=7200,   # 50:50 배정인데 72:28
        sample_size_control=2800,
        experiment_days=14,
        is_random_assignment=True,
        multiple_metrics=False,
        business_context="추천 알고리즘 변경 실험",
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp)

    print(f"\n[srm_detected] SRM={stats.srm_detected}, detail={stats.srm_detail}")
    print(f"  bias.overall_risk={bias.overall_risk}")

    assert stats.srm_detected
    assert bias.overall_risk in {"high", "medium"}


# ── 시나리오 5: no_prior_design ───────────────────────────────────────────────

def test_no_prior_design():
    """탭1 없이 탭2 진입 → violations=[], 파이프라인 정상 완료."""
    inp = ABTestInput(
        metric_name="체류시간",
        treatment_value=0.058,
        control_value=0.050,
        p_value=0.045,
        sample_size_treatment=3000,
        sample_size_control=3000,
        experiment_days=10,
        is_random_assignment=True,
        multiple_metrics=False,
        business_context="메인 배너 이미지 변경",
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp, design_ctx=None)

    print(f"\n[no_prior_design] violations={violations}, "
          f"final_recommendation={rec.final_recommendation[:60]}")

    assert violations == []
    assert rec.final_recommendation
    assert bias.overall_risk in {"low", "medium", "high"}


# ── 시나리오 6: context_loop_peeking ─────────────────────────────────────────

def test_context_loop_peeking():
    """샘플 50% 수준에서 조기 종료 → peeking 배지."""
    ctx = _make_design_ctx(target_sample_size=10000)
    inp = ABTestInput(
        metric_name="전환율",
        treatment_value=0.062,
        control_value=0.050,
        p_value=0.038,
        sample_size_treatment=2500,  # 합산 5000 = 목표의 50%
        sample_size_control=2500,
        experiment_days=7,
        is_random_assignment=True,
        multiple_metrics=False,
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp, ctx)

    print(f"\n[peeking] violations={[v.kind for v in violations]}")

    assert any(v.kind == "peeking" for v in violations)


# ── 시나리오 7: context_loop_metric_swap ──────────────────────────────────────

def test_context_loop_metric_swap():
    """1차 지표(7일_잔존율)와 다른 지표(클릭률)가 유의 → metric_swap 배지."""
    ctx = _make_design_ctx(
        primary_metric="7일_잔존율",
        agreed_mde=0.02,
        target_sample_size=8000,
    )
    inp = ABTestInput(
        metric_name="클릭률",         # 체리피킹
        treatment_value=0.065,
        control_value=0.050,
        p_value=0.018,
        sample_size_treatment=4000,
        sample_size_control=4000,
        experiment_days=14,
        is_random_assignment=True,
        multiple_metrics=True,
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp, ctx)

    print(f"\n[metric_swap] violations={[v.kind for v in violations]}")

    assert any(v.kind == "metric_swap" for v in violations)


# ── 시나리오 8: context_loop_below_mde ───────────────────────────────────────

def test_context_loop_below_mde():
    """관측 효과(+1.2pp)가 합의 MDE(5pp) 미만 → below_mde 배지."""
    ctx = _make_design_ctx(
        agreed_mde=0.05,
        baseline=0.10,
        target_sample_size=6000,
    )
    inp = ABTestInput(
        metric_name="전환율",
        treatment_value=0.112,        # +1.2pp (MDE 5pp 미달)
        control_value=0.100,
        p_value=0.041,
        sample_size_treatment=3000,
        sample_size_control=3000,
        experiment_days=14,
        is_random_assignment=True,
        multiple_metrics=False,
        provider=PROVIDER,
    )
    stats, violations, bias, rec = run_tab2_pipeline(inp, ctx)

    print(f"\n[below_mde] effect={stats.effect_size_pp:.2f}pp, "
          f"violations={[v.kind for v in violations]}")

    assert any(v.kind == "below_mde" for v in violations)
