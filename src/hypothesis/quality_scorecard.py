"""HQS v1 — 가설품질 스코어카드 (멀티턴 refinement 루프의 종료 게이트).

설계: docs/design/hypothesis-quality-scorecard.md + T1a 진단 반영(docs/design/scorecard-fillrate-diagnostic.md).
원칙:
- 채점/게이트 분리: 측정·반증 결격(★)이면 총점 무관 차단.
- LLM은 점수 생성 금지 → **룰 가이드 Y/P/N 판정만**(JUDGE_PROMPT). 점수는 결정론 룰이 매핑.
- 진단 반영: list 필드 "개수"는 입력 품질과 무관(항상 채워짐) → D4·D5는 **개수→LLM 관련성 판정**으로 전환.
- 절대 임계(80/68)는 캘리브레이션 전까지 **봉인**(기본 비활성) → 게이트 + 상대등급으로 등급.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from src.design_schemas import HypothesisOutput
from src.llm_client import LLMProvider
from src.hypothesis.scorecard_lexicons import (
    direction_rx, judge_prompt_template, judge_system, norm_token,
    vague_metric_set, vague_terms_set,
)
from src.hypothesis.scorecard_schemas import (
    DimScore, Grade, LLMJudgment, ScorecardResult,
)

# 통과조건 하한선 (failed_set 판정 — 미달 시 피드백 대상)
FLOORS = {"D1": 20, "D2": 15, "D3": 15, "D4": 12, "D5": 6, "D6": 10}
MAX = {"D1": 20, "D2": 15, "D3": 25, "D4": 20, "D5": 10, "D6": 10}
RULE_DIMS = {"D1", "D6_density"}     # 순수 결정론 (정체 보조신호용)
MAX_TURNS = {"quick": 2, "deep": 3}
D6_VAGUE_DENSITY = 0.18              # 진단 전 잠정값 — §봉인 (calibration 대상)

# 절대 총점 임계 — 캘리브레이션 전까지 봉인(기본 비활성). True로 켜면 override.
ABS_THRESHOLDS_ENABLED = False
ABS_PASS, ABS_ACCEPTABLE = 80, 68


# ─────────────────────────── 룰 차원 (결정론) ───────────────────────────
def _d1(h: HypothesisOutput, lang: str) -> DimScore:
    """측정가능성 ★게이트. measurability_confirmed 플래그는 무용(진단: 100% True)
    → 실질 신호는 '지표명이 동어반복 화이트리스트 밖의 실제 지표인가'."""
    raw = (h.suggested_primary_metric or "").strip()
    if not raw or len(raw) < 2:
        return DimScore(score=0, max=20, is_gate=True, passed=False, note="1차 지표 없음")
    vm = vague_metric_set(lang)
    words = raw.split()
    m_norm = norm_token(raw, lang)
    first_norm = norm_token(words[0], lang) if words else m_norm
    if m_norm in vm or first_norm in vm:
        return DimScore(score=10, max=20, is_gate=True, passed=False, note=f"지표 '{raw}'가 동어반복")
    return DimScore(score=20, max=20, is_gate=True, passed=True)


def _d2(h: HypothesisOutput, j: LLMJudgment, lang: str) -> DimScore:
    """반증가능성 ★게이트 = 룰(방향어휘) AND LLM(falsifiable==Y, 룰가이드)."""
    has_dir = bool(direction_rx(lang).search(h.sharpened_hypothesis or ""))
    if has_dir and j.falsifiable == "Y":
        return DimScore(score=15, max=15, is_gate=True, passed=True)
    why = "방향어휘 없음" if not has_dir else f"반증 시나리오 불가: {j.falsify_scenario or '?'}"
    return DimScore(score=0, max=15, is_gate=True, passed=False, note=why)


def _d3(h: HypothesisOutput, j: LLMJudgment) -> DimScore:
    """인과 메커니즘 = 구조(룰 0~10) + 타당성(LLM Y/P/N → 15/8/0). N이어도 구조는 살림."""
    # "개입 → 행동 → 지표" = 최소 3노드(화살표 2개). 화살표 없으면 구조 0(LLM이 타당성 보강).
    segs = [s for s in re.split(r"[-→➜>]+", h.mechanism_path or "") if s.strip()]
    if len(segs) < 3:
        struct = 0
    elif any(len(s.strip()) < 2 for s in segs):
        struct = 5
    else:
        struct = 10
    plaus = {"Y": 15, "P": 8, "N": 0}[j.mechanism_plausible]
    sc = struct + plaus
    note = "" if sc >= FLOORS["D3"] else (j.mechanism_gap or "메커니즘 약함")
    return DimScore(score=sc, max=25, passed=sc >= FLOORS["D3"], note=note)


def _d4(h: HypothesisOutput, j: LLMJudgment) -> DimScore:
    """측정정렬·리스크 — 진단 반영: 개수 아님(항상 채워짐), LLM 관련성 판정.
    교란 관련성(처치배정 AND 지표 영향) + 트레이드오프 실재. 단 list 비면 해당 부분 0."""
    conf = {"Y": 10, "P": 5, "N": 0}[j.confound_relevant] if h.confounder_candidates else 0
    trade = {"Y": 10, "P": 5, "N": 0}[j.tradeoff_real] if h.predicted_tradeoff_metrics else 0
    sc = conf + trade
    note = ""
    if sc < FLOORS["D4"]:
        miss = []
        if not h.confounder_candidates:
            miss.append("교란후보 없음")
        if not h.predicted_tradeoff_metrics:
            miss.append("트레이드오프 없음")
        note = "; ".join(miss) or j.risk_issue or "교란·트레이드오프 관련성 낮음"
    return DimScore(score=sc, max=20, passed=sc >= FLOORS["D4"], note=note)


def _d5(h: HypothesisOutput, j: LLMJudgment) -> DimScore:
    """대안탐색 — 진단 반영: 개수 아님, rejected에 '실질 사유'가 있는지 LLM 판정."""
    if not h.rejected_alternatives and not h.causal_alternative:
        return DimScore(score=0, max=10, passed=False, note="대안 검토 근거 없음")
    sc = {"Y": 10, "P": 5, "N": 0}[j.alt_justified]
    return DimScore(score=sc, max=10, passed=sc >= FLOORS["D5"], note=j.alt_issue if sc < FLOORS["D5"] else "")


def _d6(h: HypothesisOutput, j: LLMJudgment, lang: str) -> tuple[DimScore, bool]:
    """명료성 = 모호어 밀도 게이밍 차단(룰) × LLM 명료성(Y/P/N). 반환: (점수, 룰차단여부)."""
    text = h.sharpened_hypothesis or ""
    toks = text.split()
    vt = vague_terms_set(lang)
    cmp_text = text.lower()                         # 복합어·영어 대소문자 모두 substring 매칭
    density = sum(1 for term in vt if term.lower() in cmp_text) / max(len(toks), 1)
    if density >= D6_VAGUE_DENSITY:
        return DimScore(score=0, max=10, passed=False, note=f"모호어 밀도 {density:.0%} 과다"), True
    sc = {"Y": 10, "P": 5, "N": 0}[j.clarity]
    return DimScore(score=sc, max=10, passed=sc >= FLOORS["D6"], note=j.clarity_issue if sc < FLOORS["D6"] else ""), False


# ─────────────────────────── 룰 가이드 LLM judge ───────────────────────────
# 프롬프트/시스템은 lang별로 scorecard_lexicons.JUDGE_PROMPT/JUDGE_SYSTEM에 분리(i18n).


def judge_hypothesis(
    h: HypothesisOutput, *, api_key: str, provider: LLMProvider,
    lang: str = "ko", model: Optional[str] = None,
    _call: Optional[Callable] = None,
) -> LLMJudgment:
    """룰 가이드 LLM judge — 턴당 1회. _call 주입 시 테스트용 mock."""
    prompt = judge_prompt_template(lang).format(
        sharpened_hypothesis=h.sharpened_hypothesis, mechanism_path=h.mechanism_path,
        jtbd_reframe=h.jtbd_reframe, primary_metric=h.suggested_primary_metric,
        secondary="; ".join(h.suggested_secondary_metrics),
        tradeoffs="; ".join(h.predicted_tradeoff_metrics),
        confounders="; ".join(h.confounder_candidates),
        rejected="; ".join(f"{r.hypothesis}→{r.rejection_reason}" for r in h.rejected_alternatives),
    )
    if _call is None:
        from src.llm_json import call_structured
        _call = call_structured
    try:
        return _call(prompt=prompt, system=judge_system(lang), schema=LLMJudgment,
                     api_key=api_key, provider=provider, lang=lang, model=model,
                     temperature=0.0)   # 결정론 판정 → 재현성↑ (T1c: 게이트 흔들림 완화)
    except Exception as e:   # API 오류·timeout·validation 실패 → 비관적 폴백(전부 N), 파이프라인 보호
        import logging
        logging.getLogger(__name__).warning("HQS LLM judge 실패 → 비관적 폴백(N): %s", e)
        return LLMJudgment()


# ─────────────────────────── 채점 + 등급 ───────────────────────────
def score_hypothesis(
    h: HypothesisOutput, judgment: LLMJudgment, *,
    lang: str = "ko", abs_thresholds: Optional[bool] = None,
) -> ScorecardResult:
    use_abs = ABS_THRESHOLDS_ENABLED if abs_thresholds is None else abs_thresholds
    d6, d6_rule_block = _d6(h, judgment, lang)
    scores = {
        "D1": _d1(h, lang), "D2": _d2(h, judgment, lang), "D3": _d3(h, judgment),
        "D4": _d4(h, judgment), "D5": _d5(h, judgment), "D6": d6,
    }
    total = sum(s.score for s in scores.values())
    gate = scores["D1"].score == 20 and scores["D2"].score == 15
    failed = sorted(d for d in scores if scores[d].score < FLOORS[d])
    failed_rule = sorted(
        ([d for d in ("D1",) if scores[d].score < FLOORS[d]])
        + (["D6"] if d6_rule_block else [])
    )
    caveats = [f"{d}: {scores[d].note}" for d in failed if scores[d].note]

    # 등급: 게이트 우선 + 상대(기본). 절대임계는 봉인(opt-in override).
    if not gate:
        grade: Grade = "REDESIGN"
    elif use_abs:
        grade = "PASS" if (scores["D3"].score >= 15 and total >= ABS_PASS) \
            else ("ACCEPTABLE_CAVEAT" if total >= ABS_ACCEPTABLE else "REFINE")
    else:
        weak = sum(1 for d in ("D3", "D4", "D5", "D6") if not scores[d].passed)
        grade = "PASS" if weak == 0 else ("ACCEPTABLE_CAVEAT" if weak <= 2 else "REFINE")

    return ScorecardResult(
        scores=scores, total=total, gate_passed=gate, grade=grade,
        failed_set=failed, failed_rule_dims=failed_rule, caveats=caveats,
    )


# ─────────────────────────── 정체 방지 (Best-so-far Soft Pass) ───────────────────────────
def should_stop(history: list[ScorecardResult], mode: str = "quick") -> tuple[bool, str, ScorecardResult]:
    """정체 = 피드백 소진(동일 미달차원/총점하락). 항상 best-so-far(argmax 총점) 반환. Expander 롤백 안 함.

    ★ 게이트 결격(측정/반증)으로 끝나면 soft pass 아님 — best.grade가 이미 REDESIGN이라 통과 불가.
    """
    assert history, "history가 비어있다"
    cur = history[-1]
    best = max(history, key=lambda r: r.total)

    def _terminate(reason: str) -> tuple[bool, str, ScorecardResult]:
        # 누적 최고점도 게이트 결격이면 REDESIGN 유지(설계 원칙 ★ — soft pass 금지)
        if not best.gate_passed:
            return True, "게이트 결격 누적 → REDESIGN(통과 불가)", best
        return True, reason, best

    if cur.grade in ("PASS", "ACCEPTABLE_CAVEAT"):
        return True, "pass", cur
    if len(history) >= MAX_TURNS.get(mode, 2):
        return _terminate("max_turns → best-so-far soft pass + caveat")
    if len(history) >= 2 and (
        set(cur.failed_set) == set(history[-2].failed_set)
        or cur.total < history[-2].total            # 총점 하락도 정체로 간주
    ):
        return _terminate("stall(동일 결손/총점 하락) → best-so-far soft pass")
    if (len(history) >= 2 and cur.failed_rule_dims
            and set(cur.failed_rule_dims) == set(history[-2].failed_rule_dims)):
        return _terminate("stall(rule only) → best-so-far soft pass")
    return False, "continue", cur
