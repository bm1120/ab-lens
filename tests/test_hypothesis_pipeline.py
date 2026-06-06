"""탭1 가설 고도화 파이프라인 (직접 오케스트레이션, LangGraph 없음).

trivial 라우팅 → classify → (발산) → [clear: 수렴+편향 / abstract: 측정확인 대기]. Quick/Deep, 팀합의 스킵.
"""
from contextlib import ExitStack
from unittest.mock import patch

from src.hypothesis.pipeline import (
    PipelineResult, run_hypothesis_pipeline, resume_with_pinned,
)
from src.hypothesis.expander import ExpanderOutput
from src.hypothesis.classify import ConstructClassification
from src.hypothesis.measurement import (
    MeasurementProposal, ConstructMeasurement, MetricCandidate, PinnedMetrics,
)
from src.schemas import LLMProvider
from tests.test_sharpener import _hypothesis
from tests.test_bias_screener import _item
from src.design_schemas import BiasScreenResult
from src.hypothesis.trivial_router import TrivialVerdict


def _run(idea="결제 전환율 올리기", mode="quick", state="initial_idea", on_progress=None):
    return run_hypothesis_pipeline(
        idea, mode=mode, hypothesis_state=state,
        api_key="k", provider=LLMProvider.ANTHROPIC, on_progress=on_progress,
    )


def _patches(trivial=False, kind="clear"):
    constructs = [] if kind == "clear" else ["신뢰"]
    return {
        "route_trivial": patch("src.hypothesis.pipeline.route_trivial",
                               return_value=TrivialVerdict(is_trivial=trivial, reason="r")),
        "classify": patch("src.hypothesis.pipeline.classify_construct",
                          return_value=ConstructClassification(kind=kind, constructs=constructs)),
        "expand": patch("src.hypothesis.pipeline.expand",
                        return_value=ExpanderOutput(jtbd_reframe="j", implicit_assumptions=[],
                                                    candidate_hypotheses=["a", "b", "c"])),
        "measurement": patch("src.hypothesis.pipeline.propose_measurement",
                             return_value=MeasurementProposal(measurements=[
                                 ConstructMeasurement(construct_name="신뢰", conceptual_definition="d",
                                     candidates=[MetricCandidate(label="재방문율", metric_type="proportion", rationale="r")])])),
        "sharpen": patch("src.hypothesis.pipeline.sharpen", return_value=_hypothesis(raw_idea="x")),
        "screen_bias": patch("src.hypothesis.pipeline.screen_bias",
                             return_value=BiasScreenResult(biases=[_item("confirmation_bias")], active_count=1)),
    }


def _with(p, keys):
    stack = ExitStack()
    mocks = {k: stack.enter_context(p[k]) for k in keys}
    return stack, mocks


ALL = ["route_trivial", "classify", "expand", "measurement", "sharpen", "screen_bias"]


def test_trivial_short_circuits():
    p = _patches(trivial=True)
    with ExitStack() as s:
        m = {k: s.enter_context(p[k]) for k in ALL}
        out = _run()
    assert out.trivial is True and out.hypothesis is None
    m["expand"].assert_not_called()
    m["sharpen"].assert_not_called()


def test_clear_runs_full_pipeline():
    p = _patches(kind="clear")
    with ExitStack() as s:
        m = {k: s.enter_context(p[k]) for k in ALL}
        out = _run(state="initial_idea")
    assert out.trivial is False and out.hypothesis is not None and out.bias_screen is not None
    assert out.needs_measurement is False
    m["expand"].assert_called_once()
    m["measurement"].assert_not_called()   # clear는 측정확인 안 함


def test_abstract_waits_for_measurement():
    p = _patches(kind="abstract")
    with ExitStack() as s:
        m = {k: s.enter_context(p[k]) for k in ALL}
        out = _run(state="initial_idea")
    assert out.needs_measurement is True
    assert out.hypothesis is None              # 사용자 확정 전 sharpen 안 함
    assert out.measurement is not None
    assert out.expander_output is not None     # resume용 보관
    m["sharpen"].assert_not_called()


def test_team_agreed_skips_expander_clear():
    p = _patches(kind="clear")
    with ExitStack() as s:
        m = {k: s.enter_context(p[k]) for k in ALL}
        out = _run(state="team_agreed")
    m["expand"].assert_not_called()
    m["sharpen"].assert_called_once()
    assert out.hypothesis is not None


def test_resume_with_pinned_finishes():
    pinned = PinnedMetrics(primary_metric="브랜드 검색량", secondary_metrics=["직접 방문"])
    exp = ExpanderOutput(jtbd_reframe="j", implicit_assumptions=[], candidate_hypotheses=["a"])
    with patch("src.hypothesis.pipeline.sharpen", return_value=_hypothesis(raw_idea="x")) as sh, \
         patch("src.hypothesis.pipeline.screen_bias",
               return_value=BiasScreenResult(biases=[], active_count=0)):
        out = resume_with_pinned("아이디어", exp, pinned, mode="quick",
                                 api_key="k", provider=LLMProvider.ANTHROPIC)
    assert out.hypothesis is not None
    # pinned_metrics가 sharpen에 전달됐는지
    assert sh.call_args.kwargs["pinned_metrics"] is pinned


def test_progress_emits_classify_node():
    seen = []
    p = _patches(kind="clear")
    with ExitStack() as s:
        for k in ALL:
            s.enter_context(p[k])
        _run(on_progress=seen.append)
    assert "classify" in seen and "sharpener" in seen
