"""멀티모델 토론 파이프라인 (3단계).

Phase 1: Claude / GPT / Gemini 독립 sharpen (병렬)
Phase 2: 교차 비평 N×(N-1) (병렬)
Phase 3: Opus 합성 — divergence 도출+판정 내장, 짜깁기 금지

설계 근거: /tmp/ab-lens-multimodel-out/synthesis.md (3모델 토론 합성)
검증 데이터: scripts/debate_vs_single.py (abstract/anchored 케이스에서 single 구조 실패)
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from src.config import get_credential
from src.design_schemas import HypothesisOutput
from src.hypothesis.debate_schemas import (
    Critique, DebateResult, DivergencePoint,
    DraftAttempt, ModelRole, SynthesisOutput,
)
from src.hypothesis.expander import expand
from src.hypothesis.quality_scorecard import judge_hypothesis, score_hypothesis
from src.hypothesis.sharpener import sharpen
from src.hypothesis.scorecard_schemas import ScorecardResult
from src.llm_json import call_structured
from src.schemas import LLMProvider

log = logging.getLogger(__name__)

# ── Provider 슬롯 정의 ────────────────────────────────────────────────────────

_PROVIDER_ENV = {
    ModelRole.CLAUDE: ("CLAUDE_CODE_OAUTH_TOKEN", LLMProvider.CLAUDE_CODE),
    ModelRole.GPT:    ("OPENROUTER_API_KEY",       LLMProvider.OPENROUTER),
    ModelRole.GEMINI: ("OPENROUTER_API_KEY",       LLMProvider.OPENROUTER),
}

_OPENROUTER_MODELS = {
    ModelRole.GPT:    "openai/gpt-5.5-pro",          # 카탈로그 검증 (2026-06-29)
    ModelRole.GEMINI: "google/gemini-3.5-flash",  # 카탈로그 검증 (2026-06-29)
}

# 합성은 품질이 중요해서 Opus. Phase1/2는 Haiku(속도/비용).
_SYNTH_MODEL = None   # provider 기본 (Claude Code → claude-opus-4-8 or 최고급)


def _available_slots(
    primary_provider: LLMProvider,
    primary_key: str,
    _cred: Optional[Callable] = None,
) -> list[tuple[ModelRole, LLMProvider, str, Optional[str]]]:
    """사용 가능한 (role, provider, key, model_override) 슬롯 목록.

    - Claude 슬롯은 primary로 항상 포함
    - GPT/Gemini는 OPENROUTER_API_KEY 있을 때만 추가
    - 테스트에선 _cred 주입으로 대체
    """
    cred = _cred or get_credential
    slots: list[tuple[ModelRole, LLMProvider, str, Optional[str]]] = []

    # Claude 슬롯 — primary provider 사용
    slots.append((ModelRole.CLAUDE, primary_provider, primary_key, None))

    # GPT / Gemini — OpenRouter 경유
    or_key = cred("OPENROUTER_API_KEY")
    if or_key:
        slots.append((ModelRole.GPT,    LLMProvider.OPENROUTER, or_key, _OPENROUTER_MODELS[ModelRole.GPT]))
        slots.append((ModelRole.GEMINI, LLMProvider.OPENROUTER, or_key, _OPENROUTER_MODELS[ModelRole.GEMINI]))

    return slots


# ── 직렬화 헬퍼 ───────────────────────────────────────────────────────────────

def _serialize_hyp(hyp: HypothesisOutput, label: str) -> str:
    """HypothesisOutput → 자연어 마크다운. 비평자가 읽기 좋은 포맷."""
    assumptions = "\n".join(f"- {a}" for a in (hyp.implicit_assumptions or []))
    alternatives = "\n".join(
        f"- {r.hypothesis} (이유: {r.rejection_reason})" for r in (hyp.rejected_alternatives or [])
    )
    return f"""### 안 [{label}]
**날카로운 가설**
{hyp.sharpened_hypothesis}

**메커니즘 경로**
{hyp.mechanism_path}

**주요 지표**: {hyp.suggested_primary_metric}
**측정 가능**: {"예" if hyp.measurability_confirmed else "아니오"}

**핵심 가정 (암묵적)**
{assumptions or '(없음)'}

**기각한 대안**
{alternatives or '(없음)'}"""


# ── Phase 1: 독립 추론 ────────────────────────────────────────────────────────

def _draft_one(
    idea: str,
    role: ModelRole,
    provider: LLMProvider,
    api_key: str,
    model: Optional[str],
    lang: str,
    _expand_fn: Callable,
    _sharpen_fn: Callable,
    _judge_fn: Callable,
) -> DraftAttempt:
    t0 = time.monotonic()
    try:
        exp = _expand_fn(idea, api_key=api_key, provider=provider, lang=lang, model=model)
        hyp = _sharpen_fn(idea, exp, api_key=api_key, provider=provider,
                          lang=lang, mode="quick", model=model)
        judgment = _judge_fn(hyp, api_key=api_key, provider=provider, lang=lang)
        sc = score_hypothesis(hyp, judgment)
        return DraftAttempt(
            role=role, model_id=model or provider.value,
            hypothesis=hyp, scorecard=sc,
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as e:
        log.warning("Phase1 '%s' 실패: %s", role.value, e)
        return DraftAttempt(
            role=role, model_id=model or provider.value,
            error=repr(e)[:200],
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )


def _run_phase1(
    idea: str,
    slots: list[tuple[ModelRole, LLMProvider, str, Optional[str]]],
    lang: str,
    emit: Callable[[str], None],
    _expand_fn: Callable,
    _sharpen_fn: Callable,
    _judge_fn: Callable,
) -> list[DraftAttempt]:
    emit("Phase 1: 모델별 독립 추론 중...")
    drafts: list[DraftAttempt] = [None] * len(slots)  # type: ignore

    with ThreadPoolExecutor(max_workers=len(slots)) as ex:
        futures = {
            ex.submit(_draft_one, idea, role, prov, key, model, lang,
                      _expand_fn, _sharpen_fn, _judge_fn): i
            for i, (role, prov, key, model) in enumerate(slots)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            drafts[idx] = fut.result()
            role = slots[idx][0]
            d = drafts[idx]
            status = f"{d.scorecard.total}pt" if d.scorecard else f"실패({d.error[:30] if d.error else '?'})"
            emit(f"Phase1 {role.value}: {status}")

    survivors = [d for d in drafts if d.hypothesis is not None]
    emit(f"Phase 1 완료: {len(survivors)}/{len(slots)} 생존")
    return drafts


# ── Phase 1 폴백: 1개 생존 시 solo passthrough ───────────────────────────────

def _solo_passthrough(
    idea: str,
    survivor: DraftAttempt,
    all_drafts: list[DraftAttempt],
    _synthesize_fn: Callable,
    emit: Callable[[str], None],
) -> DebateResult:
    """1개만 생존 — 토론 불가. 단독안을 Phase3 프롬프트로 정제 후 반환."""
    emit("⚠ 1개만 생존 — 토론 없이 단독 정제")
    synth = _synthesize_fn(
        idea=idea,
        drafts=[survivor],
        critiques=[],
        anonymous=False,
    )
    return DebateResult(
        idea=idea,
        drafts=all_drafts,
        critiques=[],
        synthesis=synth,
        survived_count=1,
        degraded=True,
    )


# ── 만장일치 감지 ─────────────────────────────────────────────────────────────

def _is_unanimous(survivors: list[DraftAttempt]) -> bool:
    """세 안의 메커니즘 경로와 지표가 사실상 동일하면 True."""
    if len(survivors) < 2:
        return False
    metrics = {d.hypothesis.suggested_primary_metric.strip().lower()
               for d in survivors if d.hypothesis}
    mechs = {d.hypothesis.mechanism_path.strip()[:50].lower()
             for d in survivors if d.hypothesis}
    # 지표가 전부 같고 메커니즘 앞부분도 같으면 동질
    return len(metrics) == 1 and len(mechs) == 1


# ── Phase 2: 교차 비평 ────────────────────────────────────────────────────────

_CRITIQUE_SYSTEM = (
    "당신은 A/B 테스트 실험설계 심사위원이다. 자기안 방어가 아니라 냉정한 비평이 임무다. "
    "약점 지적 시 가설 문장의 특정 부분을 직접 인용하며 설명하라. "
    "피상적 비평(\"가정이 약함\") 금지. 반드시 JSON 스키마로만 답하라."
)

_CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "strengths":    {"type": "array", "items": {"type": "string"}},
        "weaknesses":   {"type": "array", "items": {"type": "string"}},
        "steal_worthy": {"type": "array", "items": {"type": "string"}},
        "fatal_flaw":   {"type": ["string", "null"]},
    },
    "required": ["strengths", "weaknesses", "steal_worthy", "fatal_flaw"],
}


def _critique_one(
    critic: DraftAttempt,
    target: DraftAttempt,
    all_survivors: list[DraftAttempt],
    provider: LLMProvider,
    api_key: str,
    model: Optional[str],
) -> Critique:
    """critic이 target을 비평. 자기안은 1줄만 노출(방어편향 차단)."""
    # 자기안 — 편향 방지 위해 가설 1줄만
    self_summary = (critic.hypothesis.sharpened_hypothesis[:80]
                    if critic.hypothesis else "(없음)")
    # 타겟 전체 자연어 직렬화
    target_text = _serialize_hyp(target.hypothesis, target.role.value.upper())  # type: ignore

    prompt = f"""[비평 과제]
critic: {critic.role.value} / target: {target.role.value}

[내 안 — 방어편향 차단을 위해 1줄만]
{self_summary}

[비평 대상 — {target.role.value.upper()} 안 전체]
{target_text}

[비평 지침]
- strengths: {target.role.value} 안이 내 안보다 명백히 나은 점. 없으면 빈 배열. 억지 칭찬 금지.
- weaknesses: D1(측정가능성)/D2(반증가능성)/인과경로 중 약점. 가설 문장 특정 부분 인용 필수.
  ❌ "가정이 약함"  ✅ "가정3 '사용자가 색상 변화를 즉시 인지'는 배너블라인드니스를 간과"
- steal_worthy: 내 최종안에 흡수할 구체 요소 (HypothesisOutput 필드명 명시)
- fatal_flaw: 채택하면 안 되는 치명적 결함 딱 1개. 반드시 D1 또는 D2 게이트 기준으로 판정. 없으면 null.
"""
    from src.llm_json import call_structured as _cs
    import pydantic

    class _CritiqueOut(pydantic.BaseModel):
        strengths: list[str]
        weaknesses: list[str]
        steal_worthy: list[str]
        fatal_flaw: Optional[str] = None

    result = _cs(
        prompt=prompt,
        schema=_CritiqueOut,
        api_key=api_key,
        provider=provider,
        system=_CRITIQUE_SYSTEM,
        model=model,
        temperature=0.3,
    )
    return Critique(
        critic_role=critic.role,
        target_role=target.role,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        steal_worthy=result.steal_worthy,
        fatal_flaw=result.fatal_flaw,
    )


def _run_phase2(
    survivors: list[DraftAttempt],
    slots: list[tuple[ModelRole, LLMProvider, str, Optional[str]]],
    emit: Callable[[str], None],
    _critique_fn: Optional[Callable] = None,
) -> list[Critique]:
    emit("Phase 2: 교차 비평 중...")
    critiques: list[Critique] = []

    # 슬롯 → (role → (provider, key, model)) 매핑
    slot_map = {role: (prov, key, model) for role, prov, key, model in slots}

    # N×(N-1) 타겟별 분리 비평
    pairs = [
        (critic, target)
        for critic in survivors
        for target in survivors
        if critic.role != target.role
    ]

    critique_fn = _critique_fn or _critique_one

    with ThreadPoolExecutor(max_workers=min(len(pairs), 4)) as ex:
        futures = {}
        for critic, target in pairs:
            prov, key, model = slot_map.get(critic.role, (LLMProvider.CLAUDE_CODE, "", None))
            fut = ex.submit(critique_fn, critic, target, survivors, prov, key, model)
            futures[fut] = (critic.role, target.role)

        for fut in as_completed(futures):
            critic_role, target_role = futures[fut]
            try:
                c = fut.result()
                critiques.append(c)
                emit(f"Phase2 {critic_role.value}→{target_role.value}: 완료")
            except Exception as e:
                log.warning("Phase2 비평 실패 %s→%s: %s", critic_role.value, target_role.value, e)
                emit(f"Phase2 {critic_role.value}→{target_role.value}: 실패")

    emit(f"Phase 2 완료: {len(critiques)}/{len(pairs)}개 비평")
    return critiques


# ── Phase 3: 합성 ─────────────────────────────────────────────────────────────

_SYNTH_SYSTEM = (
    "당신은 최종 합성자다. 독립안들과 교차비평을 받아 최선 요소를 흡수해 "
    "처음부터 다시 쓴 단일 가설을 생성한다. "
    "짜깁기(문장 잘라붙이기·다수결·한 안 그대로 선택) 절대 금지. "
    "반드시 JSON 스키마로만 답하라."
)


def _real_synthesize(
    idea: str,
    drafts: list[DraftAttempt],
    critiques: list[Critique],
    api_key: str,
    provider: LLMProvider,
    model: Optional[str],
    anonymous: bool = True,
) -> SynthesisOutput:
    """Phase 3 합성. 합성자 익명화: drafts를 A/B/C로 노출."""
    survivors = [d for d in drafts if d.hypothesis is not None]
    role_to_label = {d.role: chr(65 + i) for i, d in enumerate(survivors)}  # A/B/C
    label_to_role = {v: k for k, v in role_to_label.items()}

    # 독립안 직렬화 (익명화)
    drafts_text = "\n\n".join(
        _serialize_hyp(d.hypothesis, role_to_label[d.role])  # type: ignore
        for d in survivors
    )

    # 비평 요약 직렬화
    def _fmt_critique(c: Critique) -> str:
        critic_label = role_to_label.get(c.critic_role, c.critic_role.value)
        target_label = role_to_label.get(c.target_role, c.target_role.value)
        lines = [f"[{critic_label}→{target_label}]"]
        if c.strengths:
            lines.append(f"  강점: {'; '.join(c.strengths[:2])}")
        if c.weaknesses:
            lines.append(f"  약점: {'; '.join(c.weaknesses[:2])}")
        if c.steal_worthy:
            lines.append(f"  흡수할 것: {'; '.join(c.steal_worthy[:2])}")
        if c.fatal_flaw:
            lines.append(f"  치명적 결함: {c.fatal_flaw}")
        return "\n".join(lines)

    critiques_text = "\n".join(_fmt_critique(c) for c in critiques) or "(비평 없음)"

    import pydantic

    class _HypOut(pydantic.BaseModel):
        sharpened_hypothesis: str
        mechanism_path: str
        suggested_primary_metric: str
        falsification_condition: str
        key_assumptions: list[str] = []
        alternative_rejected: list[str] = []
        experiment_feasible: bool = True
        causal_alternative: Optional[str] = None
        measurability_confirmed: bool = True

    class _DivPoint(pydantic.BaseModel):
        axis: str
        positions: dict[str, str]
        why_it_matters: str
        verdict: str

    class _SynthOut(pydantic.BaseModel):
        final_hypothesis: _HypOut
        absorbed_from: dict[str, str]
        rejected_with_reason: dict[str, str]
        divergence_verdicts: list[_DivPoint]
        synthesis_rationale: str

    prompt = f"""[합성 과제]
아이디어: {idea}

[독립안 {len(survivors)}개]
{drafts_text}

[교차 비평]
{critiques_text}

[합성 지침 — 2단계]

1단계: 먼저 독립안들이 갈라진 축을 divergence_verdicts로 도출하라.
  각 축마다: axis(갈라진 차원) / positions(각 안 입장, 레이블 A/B/C로) /
  why_it_matters(실험설계 위험) / verdict(어느 입장 채택+이유)

2단계: 그 판정 위에서 최선 요소를 흡수해 "처음부터 다시 쓴" 가설을 작성하라.

금지:
  ❌ 한 안 그대로 선택
  ❌ 문장 잘라붙이기
  ❌ 다수결("A·B 둘 다 같은 제안" → 자동 채택 금지, 왜 더 나은지 설명해야 함)

필수 출력:
  - final_hypothesis: 재작성된 새 HypothesisOutput
  - absorbed_from: {{필드명: 레이블(A/B/C)}} 필드 단위 출처 매핑
  - rejected_with_reason: {{버린 요소: 이유}}
  - divergence_verdicts: 위 1단계
  - synthesis_rationale: "왜 짜깁기가 아닌가" 자기변론 1~3문장
"""

    from src.llm_json import call_structured as _cs

    raw = _cs(
        prompt=prompt,
        schema=_SynthOut,
        api_key=api_key,
        provider=provider,
        system=_SYNTH_SYSTEM,
        model=model,
        temperature=0.3,
    )

    # 익명 레이블 → 실제 role.value 역매핑
    absorbed_mapped = {
        field: label_to_role[label].value if label in label_to_role else label
        for field, label in raw.absorbed_from.items()
    }
    div_mapped = []
    for dv in raw.divergence_verdicts:
        positions_mapped = {
            label_to_role[lbl].value if lbl in label_to_role else lbl: pos
            for lbl, pos in dv.positions.items()
        }
        div_mapped.append(DivergencePoint(
            axis=dv.axis,
            positions=positions_mapped,
            why_it_matters=dv.why_it_matters,
            verdict=dv.verdict,
        ))

    final_hyp = HypothesisOutput(**raw.final_hypothesis.model_dump())
    return SynthesisOutput(
        final_hypothesis=final_hyp,
        absorbed_from=absorbed_mapped,
        rejected_with_reason=raw.rejected_with_reason,
        divergence_verdicts=div_mapped,
        synthesis_rationale=raw.synthesis_rationale,
    )


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def run_debate(
    idea: str,
    *,
    primary_provider: LLMProvider,
    primary_key: str,
    lang: str = "ko",
    on_progress: Optional[Callable[[str], None]] = None,
    # 테스트 주입점
    _expand: Optional[Callable] = None,
    _sharpen: Optional[Callable] = None,
    _judge: Optional[Callable] = None,
    _critique: Optional[Callable] = None,
    _synthesize: Optional[Callable] = None,
    _cred: Optional[Callable] = None,
) -> DebateResult:
    """멀티모델 토론 진입점.

    Phase 1(독립 추론) → Phase 2(교차 비평) → Phase 3(합성).
    실패 내성: 1개 생존→solo passthrough, 0개→AllModelsFailedError.
    """
    t0 = time.monotonic()
    emit = on_progress or (lambda m: None)

    expand_fn   = _expand   or expand
    sharpen_fn  = _sharpen  or sharpen
    judge_fn    = _judge    or judge_hypothesis

    slots = _available_slots(primary_provider, primary_key, _cred=_cred)
    emit(f"슬롯 {len(slots)}개: {[s[0].value for s in slots]}")

    # ── Phase 1 ──────────────────────────────────────────────────────────────
    all_drafts = _run_phase1(idea, slots, lang, emit, expand_fn, sharpen_fn, judge_fn)
    survivors = [d for d in all_drafts if d.hypothesis is not None]

    if len(survivors) == 0:
        errors = "; ".join(d.error or "?" for d in all_drafts)
        raise RuntimeError(f"모든 모델 실패: {errors}")

    degraded = len(survivors) < len(slots)

    # 합성 함수 결정 (provider는 Claude — 합성 품질 우선)
    synth_provider = primary_provider
    synth_key = primary_key

    def _do_synthesize(idea, drafts, critiques, anonymous=True):
        if _synthesize:
            # 테스트 주입 함수는 단순 시그니처 (idea, drafts, critiques)
            return _synthesize(idea=idea, drafts=drafts, critiques=critiques)
        return _real_synthesize(
            idea=idea, drafts=drafts, critiques=critiques,
            api_key=synth_key, provider=synth_provider,
            model=_SYNTH_MODEL, anonymous=anonymous,
        )

    # 1개 생존 → solo passthrough
    if len(survivors) == 1:
        result = _solo_passthrough(idea, survivors[0], all_drafts, _do_synthesize, emit)
        result.total_elapsed_ms = int((time.monotonic() - t0) * 1000)
        return result

    # 만장일치 조기종료
    if _is_unanimous(survivors):
        emit("ℹ 만장일치 — 토론 조기종료, 대표안 정제")
        synth = _do_synthesize(idea, [survivors[0]], [], anonymous=False)
        return DebateResult(
            idea=idea, drafts=all_drafts, critiques=[],
            synthesis=synth,
            survived_count=len(survivors),
            degraded=degraded,
            early_exit_unanimous=True,
            total_elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

    # ── Phase 2 ──────────────────────────────────────────────────────────────
    critiques = _run_phase2(survivors, slots, emit, _critique_fn=_critique)

    # ── Phase 3 ──────────────────────────────────────────────────────────────
    emit("Phase 3: 합성 중 (Opus)...")
    synth = _do_synthesize(idea, all_drafts, critiques, anonymous=True)

    # 합성안 스코어카드 채점
    try:
        j = judge_fn(synth.final_hypothesis, api_key=synth_key, provider=synth_provider, lang=lang)
        synth.final_scorecard = score_hypothesis(synth.final_hypothesis, j)
        emit(f"Phase 3 완료: {synth.final_scorecard.total}pt ({synth.final_scorecard.grade})")
    except Exception as e:
        log.warning("합성안 채점 실패 (비치명): %s", e)
        emit("Phase 3 완료 (채점 실패)")

    return DebateResult(
        idea=idea,
        drafts=all_drafts,
        critiques=critiques,
        synthesis=synth,
        survived_count=len(survivors),
        degraded=degraded,
        total_elapsed_ms=int((time.monotonic() - t0) * 1000),
    )
