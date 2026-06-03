"""탭1 가설 고도화 파이프라인 (직접 오케스트레이션).

3-모델 토론 결정에 따라 LangGraph 없이 in-process 직접 호출로 구성한다.
무거운 LLM 단계는 호출부(app.py)가 백그라운드 스레드로 돌리고, 각 단계 완료를
on_progress 콜백으로 알린다.

흐름:  trivial_router → [expander(초기 아이디어만)] → sharpener → bias_screener
"""
from __future__ import annotations

from typing import Callable, Literal, Optional

from pydantic import BaseModel

from src.design_schemas import BiasScreenResult, HypothesisOutput, ServiceContext
from src.hypothesis.bias_screener import screen_bias
from src.hypothesis.expander import ExpanderOutput, expand
from src.hypothesis.sharpener import sharpen
from src.hypothesis.trivial_router import route_trivial
from src.schemas import LLMProvider


class PipelineResult(BaseModel):
    trivial: bool
    trivial_reason: Optional[str] = None
    hypothesis: Optional[HypothesisOutput] = None
    bias_screen: Optional[BiasScreenResult] = None


def run_hypothesis_pipeline(
    idea: str,
    mode: Literal["quick", "deep"],
    hypothesis_state: Literal["initial_idea", "team_agreed"],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    on_progress: Optional[Callable[[str], None]] = None,
    model: str | None = None,
    service_context: ServiceContext | None = None,
) -> PipelineResult:
    def emit(node: str) -> None:
        if on_progress is not None:
            on_progress(node)

    # Stage 0: A/B 대상 여부
    verdict = route_trivial(idea, api_key=api_key, provider=provider, lang=lang, model=model)
    emit("trivial_router")
    if verdict.is_trivial:
        return PipelineResult(trivial=True, trivial_reason=verdict.reason)

    # Stage 1: 발산 (팀 합의 완료면 스킵하고 idea 를 단일 후보로)
    if hypothesis_state == "team_agreed":
        expander_output = ExpanderOutput(
            jtbd_reframe=idea, implicit_assumptions=[], candidate_hypotheses=[idea]
        )
    else:
        expander_output = expand(
            idea, api_key=api_key, provider=provider, lang=lang, model=model,
            service_context=service_context,
        )
        emit("expander")

    # Stage 2: 수렴 + 메커니즘 명시 (Deep 모드 시 2라운드 DeepCritique 포함)
    hypothesis = sharpen(
        idea, expander_output, api_key=api_key, provider=provider, lang=lang,
        mode=mode, model=model, service_context=service_context,
    )
    emit("sharpener")

    # Stage 2 편향 스크리닝 (Quick 3종 / Deep 7종)
    bias_screen = screen_bias(
        hypothesis.sharpened_hypothesis, mode=mode, api_key=api_key, provider=provider, lang=lang, model=model
    )
    emit("bias_screener")

    return PipelineResult(trivial=False, hypothesis=hypothesis, bias_screen=bias_screen)
