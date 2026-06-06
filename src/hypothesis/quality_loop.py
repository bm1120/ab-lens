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
from src.hypothesis.measurement import PinnedMetrics
from src.hypothesis.sharpener import sharpen
from src.hypothesis.bias_screener import screen_bias
from src.hypothesis.trivial_router import route_trivial
from src.hypothesis.feedback_generator import build_feedback
from src.hypothesis.quality_scorecard import (
    judge_hypothesis, score_hypothesis, should_stop,
)
from src.hypothesis.scorecard_schemas import ScorecardResult


# should_stop이 종료를 소유하지만, 버그·예외 대비 방어적 하드 리미트(should_stop의 max_turns보다 큼).
HARD_MAX_TURNS = 8


class TurnRecord(BaseModel):
    turn: int
    grade: str
    total: int
    gate_passed: bool
    failed_set: list[str]


class QualityLoopResult(BaseModel):
    trivial: bool = False
    trivial_reason: Optional[str] = None
    hypothesis: Optional[HypothesisOutput] = None        # best-so-far (게이트통과 우선, 그다음 총점)
    scorecard: Optional[ScorecardResult] = None
    bias_screen: Optional[BiasScreenResult] = None
    turns: int = 0
    best_turn: int = 0                                    # 채택된 턴(1-base)
    stop_reason: str = ""
    history: list[TurnRecord] = []


def _best_idx(pairs: list) -> int:
    """게이트 통과를 최우선, 그다음 총점 (게이트가 paramount — 결격 고득점보다 통과를 채택)."""
    return max(range(len(pairs)), key=lambda i: (pairs[i][1].gate_passed, pairs[i][1].total))


def run_quality_loop(
    idea: str,
    *,
    mode: str = "quick",
    hypothesis_state: str = "initial_idea",
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: Optional[str] = None,
    domain: Optional[str] = None,
    pinned_metrics: Optional["PinnedMetrics"] = None,   # 측정확인 확정 지표 고정(P3)
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
        exp = expand_fn(idea, api_key=api_key, provider=provider, lang=lang, model=model, domain=domain)
        emit("expander")

    pairs: list[tuple[HypothesisOutput, ScorecardResult]] = []
    refinement: Optional[dict] = None
    prev: Optional[HypothesisOutput] = None
    reason = "hard_limit"

    try:
        while len(pairs) < HARD_MAX_TURNS:            # 방어적 하드 리미트(should_stop이 보통 먼저 종료)
            turn = len(pairs) + 1
            hyp = sharpen_fn(
                idea, exp, api_key=api_key, provider=provider, lang=lang, mode=mode, model=model,
                refinement=refinement, prev_hypothesis=prev, domain=domain,
                pinned_metrics=pinned_metrics,
            )
            emit(f"sharpener#{turn}")
            # 판정은 생성 model을 안 받음 → provider별 Haiku temp=0으로 고정(T1c 검증, 비용·재현성 보존).
            judgment = judge_fn(hyp, api_key=api_key, provider=provider, lang=lang)
            sc = score_hypothesis(hyp, judgment, lang=lang)
            emit(f"scorecard#{turn}:{sc.grade}({sc.total})")
            pairs.append((hyp, sc))

            stop, reason, _ = should_stop([p[1] for p in pairs], mode)
            if stop:
                break
            # 다음 턴은 best-so-far를 기반으로 재고도화(단조 수렴 — 퇴행 방지), 피드백 주입
            bprev, bsc = pairs[_best_idx(pairs)]
            prev, refinement = bprev, build_feedback(bsc, bprev, lang=lang)
        else:                                         # while 조건 소진(하드리미트 도달, break 안 함)
            reason = "hard_limit"
    except Exception as e:                            # sharpen/judge/score 실패 → 부분결과 보존
        if not pairs:
            raise
        import logging
        logging.getLogger(__name__).warning("quality_loop 예외 → best-so-far 반환: %s", e)
        reason = f"exception:{type(e).__name__}"

    best_i = _best_idx(pairs)
    best_hyp, best_sc = pairs[best_i]
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
        turns=len(pairs), best_turn=best_i + 1, stop_reason=reason, history=history,
    )
