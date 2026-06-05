"""HQS v1 테스트 — 룰 차원 결정론 + 등급 + 정체정책 + i18n + 피드백.

LLM judge는 LLMJudgment 객체를 직접 주입(결정론 테스트). 실제 LLM 호출 없음.
"""
import pytest

from src.design_schemas import HypothesisOutput, RejectedAlternative
from src.hypothesis.scorecard_schemas import LLMJudgment, ScorecardResult
from src.hypothesis.quality_scorecard import score_hypothesis, should_stop
from src.hypothesis.feedback_generator import build_feedback


def mk_hyp(**ov) -> HypothesisOutput:
    base = dict(
        raw_idea="결제 버튼 색", jtbd_reframe="빠른 결제",
        implicit_assumptions=["색이 주목도에 영향"],
        mechanism_path="버튼 색 변경 → 주목도 상승 → 클릭 → 전환",
        confounder_candidates=["시즌성", "유입경로"],
        measurability_confirmed=True,
        sharpened_hypothesis="결제 버튼 색을 빨강으로 바꾸면 전환율이 증가한다",
        suggested_primary_metric="전환율",
        suggested_secondary_metrics=["클릭률"],
        predicted_tradeoff_metrics=["객단가"],
        experiment_feasible=True,
        rejected_alternatives=[RejectedAlternative(hypothesis="크기 변경", rejection_reason="주목도 영향 작음")],
    )
    base.update(ov)
    return HypothesisOutput(**base)


def mk_judge(**ov) -> LLMJudgment:
    base = dict(falsifiable="Y", falsify_scenario="전환율이 대조군보다 낮으면 기각",
                mechanism_plausible="Y", clarity="Y",
                confound_relevant="Y", tradeoff_real="Y", alt_justified="Y")
    base.update(ov)
    return LLMJudgment(**base)


# ── 게이트 + 등급 ──────────────────────────────────────────
def test_good_hypothesis_passes():
    r = score_hypothesis(mk_hyp(), mk_judge())
    assert r.gate_passed is True
    assert r.grade == "PASS"
    assert r.scores["D1"].score == 20 and r.scores["D2"].score == 15
    assert r.total >= 90


def test_vague_metric_fails_gate():
    r = score_hypothesis(mk_hyp(suggested_primary_metric="성공"), mk_judge())
    assert r.scores["D1"].score == 10
    assert r.gate_passed is False
    assert r.grade == "REDESIGN"


def test_empty_metric_zero_gate():
    r = score_hypothesis(mk_hyp(suggested_primary_metric=""), mk_judge())
    assert r.scores["D1"].score == 0 and r.gate_passed is False


def test_no_direction_word_fails_d2():
    # 방향어휘 없는 동어반복 문장
    r = score_hypothesis(mk_hyp(sharpened_hypothesis="버튼 색을 바꾸면 결제가 좋아진다는 가설"), mk_judge())
    assert r.scores["D2"].score == 0
    assert r.grade == "REDESIGN"


def test_falsifiable_N_fails_d2_even_with_direction():
    r = score_hypothesis(mk_hyp(), mk_judge(falsifiable="N"))
    assert r.scores["D2"].score == 0 and r.gate_passed is False


# ── D3 메커니즘: 구조(룰) + 타당성(LLM) ──────────────────────
def test_mechanism_struct_incomplete():
    r = score_hypothesis(mk_hyp(mechanism_path="버튼 변경"), mk_judge())  # 화살표 없음
    # struct=0 + plaus Y(15) = 15
    assert r.scores["D3"].score == 15


def test_mechanism_N_keeps_struct():
    r = score_hypothesis(mk_hyp(), mk_judge(mechanism_plausible="N"))
    # struct=10 + plaus N(0) = 10, D3 미통과(<15)
    assert r.scores["D3"].score == 10 and r.scores["D3"].passed is False


# ── D4/D5: 개수 아님, LLM 관련성 (진단 반영) ──────────────────
def test_d4_relevance_not_count():
    # 교란 후보 많아도 관련성 N이면 낮은 점수 (개수≠품질)
    many = ["a", "b", "c", "d", "e", "f"]
    r = score_hypothesis(mk_hyp(confounder_candidates=many), mk_judge(confound_relevant="N", tradeoff_real="N"))
    assert r.scores["D4"].score == 0


def test_d4_empty_lists_zero_part():
    r = score_hypothesis(mk_hyp(confounder_candidates=[], predicted_tradeoff_metrics=[]), mk_judge())
    assert r.scores["D4"].score == 0  # list 비면 LLM Y여도 0


def test_d5_no_alternatives_zero():
    r = score_hypothesis(mk_hyp(rejected_alternatives=[], causal_alternative=None), mk_judge())
    assert r.scores["D5"].score == 0


# ── D6 모호어 게이밍 차단 (룰) ────────────────────────────────
def test_d6_vague_density_block():
    vague = "다양한 여러 등 관련 전반 적절히 최적화 더 나은 개선 향상"
    r = score_hypothesis(mk_hyp(sharpened_hypothesis=vague), mk_judge(clarity="Y"))
    assert r.scores["D6"].score == 0  # LLM Y여도 룰이 차단


# ── i18n (영어 가설이 한국어 룰에 막히지 않아야 — PR #4 Blocker) ──
def test_i18n_english_direction_and_metric():
    h = mk_hyp(sharpened_hypothesis="Changing the CTA color to red will increase conversion rate",
               suggested_primary_metric="conversion rate",
               mechanism_path="color change -> attention -> click -> conversion")
    r = score_hypothesis(h, mk_judge(), lang="en")
    assert r.scores["D2"].score == 15   # 'increase' 매치 + falsifiable Y → 게이트 통과
    assert r.scores["D1"].score == 20
    assert r.gate_passed is True


def test_i18n_english_vague_metric():
    r = score_hypothesis(mk_hyp(suggested_primary_metric="success"), mk_judge(), lang="en")
    assert r.scores["D1"].score == 10  # 영어 동어반복 화이트리스트


# ── 상대 등급 (절대임계 봉인 기본) ────────────────────────────
def test_grade_acceptable_with_caveat():
    r = score_hypothesis(mk_hyp(), mk_judge(mechanism_plausible="P", clarity="P"))
    assert r.gate_passed is True
    assert r.grade == "ACCEPTABLE_CAVEAT"   # weak 2개


def test_grade_refine_many_weak():
    r = score_hypothesis(mk_hyp(), mk_judge(mechanism_plausible="N", clarity="N",
                                            confound_relevant="N", tradeoff_real="N", alt_justified="N"))
    assert r.gate_passed is True
    assert r.grade == "REFINE"   # weak >=3


# ── 정체 정책 ────────────────────────────────────────────────
def test_should_stop_on_pass():
    r = score_hypothesis(mk_hyp(), mk_judge())
    stop, reason, best = should_stop([r], "quick")
    assert stop and reason == "pass"


def _weak_passed():
    # 게이트는 통과(D1·D2 OK)하되 품질 약함 → REFINE (soft-pass 경로 테스트용)
    j = mk_judge(mechanism_plausible="N", clarity="N", confound_relevant="N",
                 tradeoff_real="N", alt_justified="N")
    r = score_hypothesis(mk_hyp(), j)
    assert r.gate_passed and r.grade == "REFINE"
    return r


def test_should_stop_max_turns_best_so_far():
    weak = _weak_passed()
    stop, reason, best = should_stop([weak, weak], "quick")  # quick max=2
    assert stop and "max_turns" in reason and best.gate_passed is True


def test_should_stop_feedback_exhaustion():
    weak = _weak_passed()
    stop, reason, best = should_stop([weak, weak], "deep")  # deep max=3, len 2 → stall
    assert stop and "stall" in reason


# ── 피드백 ───────────────────────────────────────────────────
def test_feedback_lists_failed_dims():
    r = score_hypothesis(mk_hyp(suggested_primary_metric="성공"), mk_judge())
    fb = build_feedback(r, mk_hyp(suggested_primary_metric="성공"))
    dims = [d["dimension"] for d in fb["failed_dimensions"]]
    assert any("D1" in d for d in dims)
    assert "절대 수정하지" in fb["refinement_directive"]


# ── cross_verify 리뷰 반영 회귀 ──────────────────────────────
def test_en_uppercase_metric_caught():
    # "Success"(대문자) 도 영어 동어반복으로 잡혀야 (cross_verify #3/#B)
    r = score_hypothesis(mk_hyp(suggested_primary_metric="Success"), mk_judge(), lang="en")
    assert r.scores["D1"].score == 10


def test_compound_vague_term_blocks_d6():
    # 복합 모호어("더 나은", "어느 정도")는 split 토큰엔 안 잡혔던 버그 (cross_verify #A)
    txt = "더 나은 결과를 어느 정도 적절히 개선하여 향상시킨다"
    r = score_hypothesis(mk_hyp(sharpened_hypothesis=txt), mk_judge(clarity="Y"))
    assert r.scores["D6"].score == 0


def test_tradeoff_P_does_not_crash_and_maps():
    # LLM이 Y/N 필드에 P를 줘도 crash 없이 처리 (cross_verify Gemini #4)
    j = mk_judge(tradeoff_real="P")
    assert j.tradeoff_real == "P"                       # 스키마가 YPN 허용
    r = score_hypothesis(mk_hyp(), j)
    # P → 5점 (Y=10), conf Y=10 → D4=15
    assert r.scores["D4"].score == 15


def test_judgment_coerces_garbage_to_N():
    from src.hypothesis.scorecard_schemas import LLMJudgment
    j = LLMJudgment(falsifiable="yes", mechanism_plausible="garbage", clarity="")
    assert j.falsifiable == "Y" and j.mechanism_plausible == "N" and j.clarity == "N"


def test_judgment_all_default_N():
    from src.hypothesis.scorecard_schemas import LLMJudgment
    j = LLMJudgment()   # judge 폴백 시 (전부 N, 비관적)
    assert j.falsifiable == "N" and j.tradeoff_real == "N"


def test_judge_uses_temperature_zero():
    # T1c 하드닝: judge는 결정론(temperature=0)으로 호출되어야 재현성↑
    from src.hypothesis.quality_scorecard import judge_hypothesis
    captured = {}

    def cap(**kw):
        captured.update(kw)
        return LLMJudgment()

    judge_hypothesis(mk_hyp(), api_key="k", provider=None, _call=cap)
    assert captured.get("temperature") == 0.0


def test_judge_pins_to_haiku_regardless_of_generation_model():
    # 생성 model을 안 넘기면 판정은 provider별 Haiku로 고정 (역할 분리: 생성↑ 판정은 저비용·결정론).
    from src.hypothesis.quality_scorecard import judge_hypothesis
    from src.schemas import LLMProvider

    cap = {}

    def grab(**kw):
        cap.update(kw)
        return LLMJudgment()

    judge_hypothesis(mk_hyp(), api_key="k", provider=LLMProvider.CLAUDE_CODE, _call=grab)
    assert cap["model"] == "claude-haiku-4-5-20251001"

    cap.clear()
    judge_hypothesis(mk_hyp(), api_key="k", provider=LLMProvider.OPENROUTER, _call=grab)
    assert cap["model"] == "anthropic/claude-haiku-4.5"


def test_judge_explicit_model_overrides_pin():
    # 명시적 model은 존중(오버라이드 탈출구).
    from src.hypothesis.quality_scorecard import judge_hypothesis
    from src.schemas import LLMProvider

    cap = {}

    def grab(**kw):
        cap.update(kw)
        return LLMJudgment()

    judge_hypothesis(mk_hyp(), api_key="k", provider=LLMProvider.CLAUDE_CODE,
                     model="claude-opus-4-8", _call=grab)
    assert cap["model"] == "claude-opus-4-8"


def test_stall_gate_failed_stays_redesign():
    # 게이트 결격으로 정체 종료 시 soft pass 아님 → REDESIGN (Gemini #1)
    bad = score_hypothesis(mk_hyp(suggested_primary_metric="성공"), mk_judge())  # gate fail
    stop, reason, best = should_stop([bad, bad], "deep")
    assert stop and best.gate_passed is False and best.grade == "REDESIGN"
    assert "REDESIGN" in reason
