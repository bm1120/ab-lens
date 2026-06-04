"""T3 — 가설 고도화 멀티턴 루프.

가설품질 스코어카드(HQS)가 통과(PASS/ACCEPTABLE)되거나 정체(Best-so-far)될 때까지
sharpener를 피드백과 함께 재호출한다. expander는 1회만(롤백 안 함, 설계 원칙).

흐름: trivial → expand(1회) → [sharpen → judge → score → (미달이면) feedback]* → bias_screen.
종료는 should_stop이 소유(통과/정체/max_turns). 항상 best-so-far(최고 총점) 반환.
"""
from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from src.design_schemas import BiasScreenResult, HypothesisOutput
from src.llm_client import LLMProvider
from src.hypothesis.expander import ExpanderOutput, expand
from src.hypothesis.sharpener import sharpen
from src.hypothesis.bias_screener import screen_bias
from src.hypothesis.trivial_router import route_trivial
from src.hypothesis.feedback_generator import build_feedback
from src.hypothesis.quality_scorecard import (
    judge_hypothesis, score_hypothesis, should_stop,
)
from src.hypothesis.scorecard_schemas import ScorecardResult


class TurnRecord(BaseModel):
    turn: int
    grade: str
    total: int
    gate_passed: bool
    failed_set: list[str]


class QualityLoopResult(BaseModel):
    trivial: bool = False
    trivial_reason: Optional[str] = None
    hypothesis: Optional[HypothesisOutput] = None        # best-so-far
    scorecard: Optional[ScorecardResult] = None
    bias_screen: Optional[BiasScreenResult] = None
    turns: int = 0
    stop_reason: str = ""
    history: list[TurnRecord] = []


def run_quality_loop(
    idea: str,
    *,
    mode: str = "quick",
    hypothesis_state: str = "initial_idea",
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
    # 테스트 주입용 (실제 LLM 호출 대체)
    _sharpen: Optional[Callable] = None,
    _judge: Optional[Callable] = None,
    _bias: Optional[Callable] = None,
    _route: Optional[Callable] = None,
    _expand: Optional[Callable] = None,
) -> QualityLoopResult:
    emit = on_progress or (lambda n: None)
    sharpen_fn = _sharpen or sharpen
    judge_fn = _judge or judge_hypothesis
    bias_fn = _bias or screen_bias
    route_fn = _route or route_trivial
    expand_fn = _expand or expand

    verdict = route_fn(idea, api_key=api_key, provider=provider, lang=lang, model=model)
    if verdict.is_trivial:
        return QualityLoopResult(trivial=True, trivial_reason=verdict.reason)

    if hypothesis_state == "team_agreed":
        exp = ExpanderOutput(jtbd_reframe=idea, implicit_assumptions=[], candidate_hypotheses=[idea])
    else:
        exp = expand_fn(idea, api_key=api_key, provider=provider, lang=lang, model=model)
        emit("expander")

    pairs: list[tuple[HypothesisOutput, ScorecardResult]] = []
    refinement: Optional[dict] = None
    prev: Optional[HypothesisOutput] = None

    while True:
        turn = len(pairs) + 1
        hyp = sharpen_fn(
            idea, exp, api_key=api_key, provider=provider, lang=lang, mode=mode, model=model,
            refinement=refinement, prev_hypothesis=prev,
        )
        emit(f"sharpener#{turn}")
        judgment = judge_fn(hyp, api_key=api_key, provider=provider, lang=lang, model=model)
        sc = score_hypothesis(hyp, judgment, lang=lang)
        emit(f"scorecard#{turn}:{sc.grade}({sc.total})")
        pairs.append((hyp, sc))

        stop, reason, best_sc = should_stop([p[1] for p in pairs], mode)
        if stop:
            break
        prev = hyp
        refinement = build_feedback(sc, hyp, lang=lang)

    best_hyp, _ = max(pairs, key=lambda p: p[1].total)
    bias_screen = bias_fn(
        best_hyp.sharpened_hypothesis, mode=mode, api_key=api_key, provider=provider, lang=lang, model=model
    )
    emit("bias_screener")

    history = [
        TurnRecord(turn=i + 1, grade=sc.grade, total=sc.total,
                   gate_passed=sc.gate_passed, failed_set=sc.failed_set)
        for i, (_, sc) in enumerate(pairs)
    ]
    return QualityLoopResult(
        hypothesis=best_hyp, scorecard=best_sc, bias_screen=bias_screen,
        turns=len(pairs), stop_reason=reason, history=history,
    )
