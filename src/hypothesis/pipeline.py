"""탭1 가설 고도화 파이프라인 (직접 오케스트레이션).

3-모델 토론 결정에 따라 LangGraph 없이 in-process 직접 호출로 구성한다.
무거운 LLM 단계는 호출부(app.py)가 백그라운드 스레드로 돌리고, 각 단계 완료를
on_progress 콜백으로 알린다.

흐름:
  trivial_router → classify
    ├─ clear         → [expander] → sharpener → bias_screener  (자동)
    └─ abstract|mixed → [expander] → measurement → (중간 반환, 사용자 측정확인 대기)
                          → resume_with_pinned(확정 지표) → sharpener → bias_screener
"""
from __future__ import annotations

from typing import Callable, Literal, Optional

from pydantic import BaseModel

from src.design_schemas import BiasScreenResult, HypothesisOutput
from src.hypothesis.bias_screener import screen_bias
from src.hypothesis.classify import ConstructClassification, classify_construct
from src.hypothesis.expander import ExpanderOutput, expand
from src.hypothesis.measurement import MeasurementProposal, PinnedMetrics, propose_measurement
from src.hypothesis.sharpener import sharpen
from src.hypothesis.trivial_router import route_trivial
from src.schemas import LLMProvider


class PipelineResult(BaseModel):
    trivial: bool
    trivial_reason: Optional[str] = None
    hypothesis: Optional[HypothesisOutput] = None
    bias_screen: Optional[BiasScreenResult] = None
    # 추상 구성개념 감지 시 측정 확인 대기 상태 (P2)
    needs_measurement: bool = False
    classification: Optional[ConstructClassification] = None
    measurement: Optional[MeasurementProposal] = None
    expander_output: Optional[ExpanderOutput] = None   # resume 재개용


def _expander_for(idea, hypothesis_state, *, api_key, provider, lang, model, emit) -> ExpanderOutput:
    if hypothesis_state == "team_agreed":
        return ExpanderOutput(jtbd_reframe=idea, implicit_assumptions=[], candidate_hypotheses=[idea])
    out = expand(idea, api_key=api_key, provider=provider, lang=lang, model=model)
    emit("expander")
    return out


def _finish(idea, expander_output, *, mode, api_key, provider, lang, model, emit,
            pinned_metrics=None, classification=None) -> PipelineResult:
    hypothesis = sharpen(idea, expander_output, api_key=api_key, provider=provider,
                         lang=lang, mode=mode, model=model, pinned_metrics=pinned_metrics)
    emit("sharpener")
    bias = screen_bias(hypothesis.sharpened_hypothesis, mode=mode, api_key=api_key,
                       provider=provider, lang=lang, model=model)
    emit("bias_screener")
    return PipelineResult(trivial=False, hypothesis=hypothesis, bias_screen=bias,
                          classification=classification)


def run_hypothesis_pipeline(
    idea: str,
    mode: Literal["quick", "deep"],
    hypothesis_state: Literal["initial_idea", "team_agreed"],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    on_progress: Optional[Callable[[str], None]] = None,
    model: str | None = None,
    domain_context: str = "",
) -> PipelineResult:
    def emit(node: str) -> None:
        if on_progress is not None:
            on_progress(node)

    # Stage 0: A/B 대상 여부
    verdict = route_trivial(idea, api_key=api_key, provider=provider, lang=lang, model=model)
    emit("trivial_router")
    if verdict.is_trivial:
        return PipelineResult(trivial=True, trivial_reason=verdict.reason)

    # Stage 0.5: 추상 구성개념 분류 (라우팅)
    classification = classify_construct(idea, api_key=api_key, provider=provider, lang=lang, model=model)
    emit("classify")

    # Stage 1: 발산
    expander_output = _expander_for(idea, hypothesis_state, api_key=api_key, provider=provider,
                                    lang=lang, model=model, emit=emit)

    # 추상/혼합 → 측정 확인 대기 (UI가 사용자 확정 후 resume_with_pinned 호출)
    if classification.kind in ("abstract", "mixed"):
        proposal = propose_measurement(
            idea, classification.constructs or [idea], domain_context,
            api_key=api_key, provider=provider, lang=lang, model=model,
        )
        emit("measurement")
        return PipelineResult(trivial=False, needs_measurement=True, classification=classification,
                              measurement=proposal, expander_output=expander_output)

    # clear → 자동 진행
    return _finish(idea, expander_output, mode=mode, api_key=api_key, provider=provider,
                   lang=lang, model=model, emit=emit, classification=classification)


def resume_with_pinned(
    idea: str,
    expander_output: ExpanderOutput,
    pinned_metrics: PinnedMetrics,
    mode: Literal["quick", "deep"],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    on_progress: Optional[Callable[[str], None]] = None,
    model: str | None = None,
) -> PipelineResult:
    """측정 확인 게이트 통과 후, 사용자 확정 지표를 고정 주입해 고도화를 마무리한다."""
    def emit(node: str) -> None:
        if on_progress is not None:
            on_progress(node)

    return _finish(idea, expander_output, mode=mode, api_key=api_key, provider=provider,
                   lang=lang, model=model, emit=emit, pinned_metrics=pinned_metrics)
