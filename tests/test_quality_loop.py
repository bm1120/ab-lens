"""T3 멀티턴 루프 테스트 — route/expand/sharpen/judge/bias를 mock 주입(실제 LLM 없음).

검증: trivial 차단 / 1턴 통과 / 재고도화 후 통과(피드백 주입) / 게이트결격 정체→REDESIGN.
"""
from src.design_schemas import HypothesisOutput, RejectedAlternative, BiasScreenResult
from src.hypothesis.expander import ExpanderOutput
from src.hypothesis.trivial_router import TrivialVerdict
from src.hypothesis.scorecard_schemas import LLMJudgment
from src.hypothesis.quality_loop import run_quality_loop


def good_hyp(metric="전환율") -> HypothesisOutput:
    return HypothesisOutput(
        raw_idea="버튼", jtbd_reframe="빠른 결제", implicit_assumptions=["a"],
        mechanism_path="버튼 색 변경 → 주목도 → 클릭 → 전환",
        confounder_candidates=["시즌성", "유입경로"], measurability_confirmed=True,
        sharpened_hypothesis="버튼 색을 빨강으로 바꾸면 전환율이 증가한다",
        suggested_primary_metric=metric, suggested_secondary_metrics=["클릭률"],
        predicted_tradeoff_metrics=["객단가"], experiment_feasible=True,
        rejected_alternatives=[RejectedAlternative(hypothesis="크기", rejection_reason="영향 작음")],
    )


GOOD = LLMJudgment(falsifiable="Y", mechanism_plausible="Y", clarity="Y",
                   confound_relevant="Y", tradeoff_real="Y", alt_justified="Y")
WEAK = LLMJudgment(falsifiable="Y", mechanism_plausible="N", clarity="N",
                   confound_relevant="N", tradeoff_real="N", alt_justified="N")  # 게이트는 통과, 품질 약함

route_ok = lambda *a, **k: TrivialVerdict(is_trivial=False, reason="")
exp_fn = lambda *a, **k: ExpanderOutput(jtbd_reframe="j", implicit_assumptions=[], candidate_hypotheses=["c"])
bias_fn = lambda *a, **k: BiasScreenResult(biases=[], active_count=0)


def test_loop_trivial_blocks():
    r = run_quality_loop("그냥 오타 수정", api_key="k", provider=None,
                         _route=lambda *a, **k: TrivialVerdict(is_trivial=True, reason="just do it"),
                         _expand=exp_fn, _sharpen=lambda *a, **k: good_hyp(),
                         _judge=lambda *a, **k: GOOD, _bias=bias_fn)
    assert r.trivial is True and r.hypothesis is None


def test_loop_pass_first_turn():
    r = run_quality_loop("아이디어", mode="quick", api_key="k", provider=None,
                         _route=route_ok, _expand=exp_fn,
                         _sharpen=lambda *a, **k: good_hyp(), _judge=lambda *a, **k: GOOD, _bias=bias_fn)
    assert r.turns == 1
    assert r.scorecard.grade == "PASS"
    assert r.bias_screen is not None


def test_loop_refine_then_pass_injects_feedback():
    st = {"t": 0, "refs": []}

    def sh(idea, e, *, refinement=None, prev_hypothesis=None, **k):
        st["t"] += 1
        st["refs"].append(refinement)
        return good_hyp()

    def jg(h, **k):
        return WEAK if st["t"] == 1 else GOOD   # 1턴 약함 → REFINE, 2턴 통과

    r = run_quality_loop("아이디어", mode="deep", api_key="k", provider=None,
                         _route=route_ok, _expand=exp_fn, _sharpen=sh, _judge=jg, _bias=bias_fn)
    assert r.turns == 2
    assert r.scorecard.grade == "PASS"
    assert st["refs"][0] is None            # 1턴엔 피드백 없음
    assert st["refs"][1] is not None        # 2턴엔 스코어카드 피드백 주입됨
    assert "failed_dimensions" in st["refs"][1]


def test_loop_gate_fail_ends_redesign():
    # 지표가 동어반복("성공") → 게이트 결격이 매턴 반복 → best-so-far도 REDESIGN
    r = run_quality_loop("아이디어", mode="quick", api_key="k", provider=None,
                         _route=route_ok, _expand=exp_fn,
                         _sharpen=lambda *a, **k: good_hyp(metric="성공"),
                         _judge=lambda *a, **k: GOOD, _bias=bias_fn)
    assert r.scorecard.gate_passed is False
    assert r.scorecard.grade == "REDESIGN"
    assert r.turns == 2                       # quick max_turns
    assert "REDESIGN" in r.stop_reason


def test_loop_history_records_turns():
    r = run_quality_loop("아이디어", mode="quick", api_key="k", provider=None,
                         _route=route_ok, _expand=exp_fn,
                         _sharpen=lambda *a, **k: good_hyp(), _judge=lambda *a, **k: GOOD, _bias=bias_fn)
    assert len(r.history) == r.turns
    assert r.history[0].grade == "PASS"
