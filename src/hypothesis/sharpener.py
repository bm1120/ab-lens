"""HypothesisSharpener (Stage 2) — Validator 이식.

발산된 후보를 1~2개로 수렴(Adversarial Refinement)하고, Pearl's ladder 대신
메커니즘 명시(개입→행동→지표) + 혼란변수 + 측정 가능성을 강제한다.
기각된 후보는 rejected_alternatives 에 Decision Log 로 남긴다.
"""
from __future__ import annotations

from src.design_schemas import HypothesisOutput
from src.hypothesis.expander import ExpanderOutput
from src.llm_json import call_structured
from src.schemas import LLMProvider

SYSTEM_KO = (
    "당신은 A/B 테스트 가설 정련 전문가입니다. 발산된 후보들을 적대적으로 검증해 "
    "1~2개로 수렴시키세요. 각 가설은 메커니즘(개입→행동 변화→지표)을 명시하고, "
    "혼란변수 후보를 1개 이상 들고, 측정 가능성을 확인해야 합니다. "
    "측정 불가/편향 과다/범위 과다인 후보는 rejected_alternatives 에 사유와 함께 기록하세요. "
    "사실 수치(baseline/트래픽)는 절대 지어내지 말고 지표 '제안'만 하세요. "
    "experiment_feasible 가 false 면 causal_alternative 에 DiD/PSM 조건을 적으세요. "
    "반드시 HypothesisOutput JSON 스키마로만 답하세요."
)
SYSTEM_EN = (
    "You are an A/B test hypothesis refiner. Adversarially validate the diverged "
    "candidates and converge to 1-2. Each hypothesis must state its mechanism "
    "(intervention→behavior change→metric), list >=1 confounder candidate, and confirm "
    "measurability. Record unmeasurable/over-biased/over-scoped candidates in "
    "rejected_alternatives with reasons. NEVER fabricate factual numbers "
    "(baseline/traffic); only SUGGEST metrics. If experiment_feasible is false, put "
    "DiD/PSM conditions in causal_alternative. Answer ONLY as HypothesisOutput JSON."
)


def _build_prompt(idea: str, exp: ExpanderOutput) -> str:
    return (
        f"원 아이디어: {idea}\n"
        f"JTBD: {exp.jtbd_reframe}\n"
        f"암묵적 전제: {exp.implicit_assumptions}\n"
        f"발산된 후보:\n" + "\n".join(f"- {c}" for c in exp.candidate_hypotheses)
    )


def sharpen(
    idea: str,
    expander_output: ExpanderOutput,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
) -> HypothesisOutput:
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    out = call_structured(
        prompt=_build_prompt(idea, expander_output),
        system=system,
        schema=HypothesisOutput,
        api_key=api_key,
        provider=provider,
        lang=lang,
    )
    # LLM 이 raw_idea 를 빠뜨려도 입력값으로 강제 (이월 정합)
    return out.model_copy(update={"raw_idea": idea})
