"""HypothesisSharpener (Stage 2) — Validator 이식.

발산된 후보를 1~2개로 수렴(Adversarial Refinement)하고, Pearl's ladder 대신
메커니즘 명시(개입→행동→지표) + 혼란변수 + 측정 가능성을 강제한다.
기각된 후보는 rejected_alternatives 에 Decision Log 로 남긴다.

Deep 모드: 1라운드 수렴 후 2라운드 Adversarial Refinement(DeepCritique)를 추가로 수행한다.
- 반례(counter-example) 1개 이상 제시 시도
- 가설이 틀릴 수 있는 조건 명시
- 최종 가설 강화 또는 rejected_alternatives에 추가하고 대안 채택
"""
from __future__ import annotations

from typing import Literal

from src.design_schemas import HypothesisOutput, RejectedAlternative
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

SYSTEM_DEEP_KO = (
    "당신은 A/B 테스트 가설 비평 전문가입니다. 제시된 가설을 적대적으로 공격해 "
    "결함을 찾아내세요. 반드시 다음을 수행하세요: "
    "1) 반례(counter-example) 1개 이상 제시 — 이 가설이 틀릴 수 있는 실제 시나리오. "
    "2) 가설이 실패하는 조건 명시 (confounder_candidates에 추가). "
    "3) 비판 후 가설이 유효하면 sharpened_hypothesis를 더 구체적으로 강화하고, "
    "   유효하지 않으면 rejected_alternatives에 기각 사유를 추가하고 대안 가설로 교체. "
    "4) mechanism_path와 측정 지표는 1라운드 결과를 유지하되 필요시 개선. "
    "반드시 HypothesisOutput JSON 스키마로만 답하세요."
)
SYSTEM_DEEP_EN = (
    "You are an A/B test hypothesis critic. Adversarially attack the provided hypothesis "
    "to find flaws. You must: "
    "1) Provide >=1 counter-example — real scenarios where this hypothesis could be wrong. "
    "2) State conditions under which the hypothesis fails (add to confounder_candidates). "
    "3) After critique, if the hypothesis is still valid, strengthen sharpened_hypothesis "
    "   to be more specific; if invalid, add to rejected_alternatives with rejection reason "
    "   and adopt an alternative hypothesis. "
    "4) Preserve mechanism_path and metrics from round 1, improve if needed. "
    "Answer ONLY as HypothesisOutput JSON."
)


def _service_context_block(service_context: object, lang: str) -> str:
    """ServiceContext를 시스템 프롬프트에 주입할 텍스트 블록으로 변환한다."""
    if lang == "ko":
        return (
            "\n\n[서비스 컨텍스트 — 수렴 시 반드시 반영]\n"
            f"서비스명: {service_context.service_name}\n"  # type: ignore[union-attr]
            f"타깃 사용자: {service_context.target_users}\n"  # type: ignore[union-attr]
            f"주요 지표: {service_context.primary_metric}\n"  # type: ignore[union-attr]
            f"현재 베이스라인: {service_context.current_baseline}\n"  # type: ignore[union-attr]
            f"과거 실험: {service_context.past_experiments}\n"  # type: ignore[union-attr]
            f"도메인 제약: {service_context.domain_constraints}"  # type: ignore[union-attr]
        )
    return (
        "\n\n[Service Context — must reflect in convergence]\n"
        f"Service Name: {service_context.service_name}\n"  # type: ignore[union-attr]
        f"Target Users: {service_context.target_users}\n"  # type: ignore[union-attr]
        f"Primary Metric: {service_context.primary_metric}\n"  # type: ignore[union-attr]
        f"Current Baseline: {service_context.current_baseline}\n"  # type: ignore[union-attr]
        f"Past Experiments: {service_context.past_experiments}\n"  # type: ignore[union-attr]
        f"Domain Constraints: {service_context.domain_constraints}"  # type: ignore[union-attr]
    )


def _build_prompt(idea: str, exp: ExpanderOutput) -> str:
    return (
        f"원 아이디어: {idea}\n"
        f"JTBD: {exp.jtbd_reframe}\n"
        f"암묵적 전제: {exp.implicit_assumptions}\n"
        f"발산된 후보:\n" + "\n".join(f"- {c}" for c in exp.candidate_hypotheses)
    )


def _build_deep_critique_prompt(idea: str, round1: HypothesisOutput) -> str:
    rejected_str = (
        "\n".join(
            f"  - {r.hypothesis}: {r.rejection_reason}"
            for r in round1.rejected_alternatives
        )
        if round1.rejected_alternatives
        else "  없음"
    )
    return (
        f"원 아이디어: {idea}\n"
        f"[1라운드 수렴 결과]\n"
        f"sharpened_hypothesis: {round1.sharpened_hypothesis}\n"
        f"mechanism_path: {round1.mechanism_path}\n"
        f"confounder_candidates: {round1.confounder_candidates}\n"
        f"suggested_primary_metric: {round1.suggested_primary_metric}\n"
        f"experiment_feasible: {round1.experiment_feasible}\n"
        f"기각된 대안:\n{rejected_str}\n\n"
        f"위 가설을 적대적으로 비판하고, 반례와 실패 조건을 찾아내어 "
        f"최종 HypothesisOutput을 반환하세요."
    )


def sharpen(
    idea: str,
    expander_output: ExpanderOutput,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    mode: Literal["quick", "deep"] = "quick",
    model: str | None = None,
    service_context: object | None = None,
) -> HypothesisOutput:
    # Round 1: 기존 수렴 + 메커니즘 명시
    system = SYSTEM_KO if lang == "ko" else SYSTEM_EN
    if service_context is not None:
        system = system + _service_context_block(service_context, lang)
    out = call_structured(
        prompt=_build_prompt(idea, expander_output),
        system=system,
        schema=HypothesisOutput,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )
    # LLM 이 raw_idea 를 빠뜨려도 입력값으로 강제 (이월 정합)
    out = out.model_copy(update={"raw_idea": idea})

    if mode == "deep":
        # Round 2: DeepCritique — 1라운드 결과를 적대적으로 재검증
        system_deep = SYSTEM_DEEP_KO if lang == "ko" else SYSTEM_DEEP_EN
        if service_context is not None:
            system_deep = system_deep + _service_context_block(service_context, lang)
        out2 = call_structured(
            prompt=_build_deep_critique_prompt(idea, out),
            system=system_deep,
            schema=HypothesisOutput,
            api_key=api_key,
            provider=provider,
            lang=lang,
            model=model,
        )
        out = out2.model_copy(update={"raw_idea": idea})

    return out
