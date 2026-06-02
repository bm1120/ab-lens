"""탭1 가설 고도화 파이프라인 (직접 오케스트레이션, LangGraph 없음).

trivial 라우팅 → (발산) → 수렴 → 편향 스크리닝. Quick/Deep, 팀합의 스킵.
"""
from unittest.mock import patch

import pytest

from src.hypothesis.pipeline import PipelineResult, run_hypothesis_pipeline
from src.hypothesis.expander import ExpanderOutput
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


def _patches(trivial=False):
    return {
        "route_trivial": patch("src.hypothesis.pipeline.route_trivial",
                               return_value=TrivialVerdict(is_trivial=trivial, reason="r")),
        "expand": patch("src.hypothesis.pipeline.expand",
                        return_value=ExpanderOutput(jtbd_reframe="j", implicit_assumptions=[],
                                                    candidate_hypotheses=["a", "b", "c"])),
        "sharpen": patch("src.hypothesis.pipeline.sharpen", return_value=_hypothesis(raw_idea="x")),
        "screen_bias": patch("src.hypothesis.pipeline.screen_bias",
                             return_value=BiasScreenResult(biases=[_item("confirmation_bias")], active_count=1)),
    }


def test_trivial_short_circuits():
    p = _patches(trivial=True)
    with p["route_trivial"], p["expand"] as e, p["sharpen"] as s, p["screen_bias"]:
        out = _run()
    assert out.trivial is True
    assert out.hypothesis is None
    e.assert_not_called()   # 발산/수렴 안 함
    s.assert_not_called()


def test_initial_idea_runs_full_pipeline():
    p = _patches()
    with p["route_trivial"], p["expand"] as e, p["sharpen"] as s, p["screen_bias"]:
        out = _run(state="initial_idea")
    assert out.trivial is False
    assert out.hypothesis is not None
    assert out.bias_screen is not None
    e.assert_called_once()  # 초기 아이디어 → 발산 수행


def test_team_agreed_skips_expander():
    p = _patches()
    with p["route_trivial"], p["expand"] as e, p["sharpen"] as s, p["screen_bias"]:
        out = _run(state="team_agreed")
    e.assert_not_called()   # 팀 합의 완료 → 발산 스킵
    s.assert_called_once()  # 수렴은 수행
    assert out.hypothesis is not None


def test_progress_callback_emits_nodes():
    seen = []
    p = _patches()
    with p["route_trivial"], p["expand"], p["sharpen"], p["screen_bias"]:
        _run(on_progress=seen.append)
    assert "sharpener" in seen and "bias_screener" in seen
