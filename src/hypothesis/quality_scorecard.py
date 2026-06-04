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
    direction_rx, vague_metric_set, vague_terms_set,
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
    m = (h.suggested_primary_metric or "").strip()
    if not m or len(m) < 2:
        return DimScore(score=0, max=20, is_gate=True, passed=False, note="1차 지표 없음")
    first = m.split()[0] if m.split() else m
    if m in vague_metric_set(lang) or first in vague_metric_set(lang):
        return DimScore(score=10, max=20, is_gate=True, passed=False, note=f"지표 '{m}'가 동어반복")
    return DimScore(score=20, max=20, is_gate=True, passed=True, note="")


def _d2(h: HypothesisOutput, j: LLMJudgment, lang: str) -> DimScore:
    """반증가능성 ★게이트 = 룰(방향어휘) AND LLM(falsifiable==Y, 룰가이드)."""
    has_dir = bool(direction_rx(lang).search(h.sharpened_hypothesis or ""))
    if has_dir and j.falsifiable == "Y":
        return DimScore(score=15, max=15, is_gate=True, passed=True)
    why = "방향어휘 없음" if not has_dir else f"반증 시나리오 불가: {j.falsify_scenario or '?'}"
    return DimScore(score=0, max=15, is_gate=True, passed=False, note=why)


def _d3(h: HypothesisOutput, j: LLMJudgment) -> DimScore:
    """인과 메커니즘 = 구조(룰 0~10) + 타당성(LLM Y/P/N → 15/8/0). N이어도 구조는 살림."""
    segs = [s for s in re.split(r"[→\-➜>]+", h.mechanism_path or "") if s.strip()]
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
    trade = (10 if j.tradeoff_real == "Y" else 0) if h.predicted_tradeoff_metrics else 0
    sc = conf + trade
    return DimScore(score=sc, max=20, passed=sc >= FLOORS["D4"], note=j.risk_issue if sc < FLOORS["D4"] else "")


def _d5(h: HypothesisOutput, j: LLMJudgment) -> DimScore:
    """대안탐색 — 진단 반영: 개수 아님, rejected에 '실질 사유'가 있는지 LLM 판정."""
    if not h.rejected_alternatives and not h.causal_alternative:
        return DimScore(score=0, max=10, passed=False, note="대안 검토 근거 없음")
    sc = {"Y": 10, "P": 5, "N": 0}[j.alt_justified]
    return DimScore(score=sc, max=10, passed=sc >= FLOORS["D5"], note=j.alt_issue if sc < FLOORS["D5"] else "")


def _d6(h: HypothesisOutput, j: LLMJudgment, lang: str) -> tuple[DimScore, bool]:
    """명료성 = 모호어 밀도 게이밍 차단(룰) × LLM 명료성(Y/P/N). 반환: (점수, 룰차단여부)."""
    toks = (h.sharpened_hypothesis or "").split()
    vt = vague_terms_set(lang)
    density = sum(t.strip(".,!?") in vt for t in toks) / max(len(toks), 1)
    if density >= D6_VAGUE_DENSITY:
        return DimScore(score=0, max=10, passed=False, note=f"모호어 밀도 {density:.0%} 과다"), True
    sc = {"Y": 10, "P": 5, "N": 0}[j.clarity]
    return DimScore(score=sc, max=10, passed=sc >= FLOORS["D6"], note=j.clarity_issue if sc < FLOORS["D6"] else ""), False


# ─────────────────────────── 룰 가이드 LLM judge ───────────────────────────
JUDGE_SYSTEM = (
    "너는 가설 품질 판정자다. **점수(숫자)를 생성하지 마라.** 아래 각 항목의 판정 규칙을 그대로 적용해 "
    "Y/P/N(또는 Y/N)과 1줄 근거만 낸다. 규칙을 벗어난 임의 판단 금지."
)

JUDGE_PROMPT = """다음 가설을 항목별 **판정 규칙**대로만 판정하라.

[falsifiable] (Y/N) — 규칙: '이 가설이 틀렸다'고 판명날 **구체적 관측 시나리오를 1문장으로 쓸 수 있을 때만 Y**.
  쓸 수 없거나 동어반복("성공률이 오른다")이면 N. Y면 falsify_scenario에 그 1문장.

[mechanism_plausible] (Y/P/N) — 규칙: 개입→행동→지표의 **화살표를 하나씩** 본다.
  Y=모든 링크가 인과적이고 비약 없음 / P=정확히 한 링크가 미진술 가정 필요(복구가능) / N=링크 누락 또는 상관관계를 인과로 둔갑 또는 약한 링크 2개+. P/N이면 mechanism_gap에 끊긴 링크.

[clarity] (Y/P/N) — 규칙: Y=단일 개입 + 단일 1차지표 + 방향 명시 + 해석 유일 / P=대체로 명확하나 모호 요소 1개 / N=다의적·복합. clarity_issue에 사유.

[confound_relevant] (Y/P/N) — 규칙: 나열된 교란후보가 **처치 배정 AND 지표 둘 다에 그럴듯하게 영향**을 주는가.
  Y=그런 후보 2개+ / P=1개 / N=일반론·무관. (개수 자체는 무시, 관련성만)

[tradeoff_real] (Y/N) — 규칙: 나열된 트레이드오프 중 **1차 지표가 개선될 때 실제로 악화될 수 있는 가드레일**이 1개+ 있으면 Y, 무관/없으면 N.

[alt_justified] (Y/P/N) — 규칙: rejected_alternatives에 '왜 이 가설이 나은지' **실질 사유**가 있나.
  Y=실질 사유 1개+ / P=빈약("더 나쁨" 수준) / N=없음.

confound_relevant·tradeoff_real·alt_justified 근거는 risk_issue·alt_issue에 1줄.

가설: {sharpened_hypothesis}
메커니즘: {mechanism_path}
JTBD: {jtbd_reframe}
1차지표: {primary_metric}
보조지표: {secondary}
트레이드오프: {tradeoffs}
교란후보: {confounders}
기각대안: {rejected}
"""


def judge_hypothesis(
    h: HypothesisOutput, *, api_key: str, provider: LLMProvider,
    lang: str = "ko", model: Optional[str] = None,
    _call: Optional[Callable] = None,
) -> LLMJudgment:
    """룰 가이드 LLM judge — 턴당 1회. _call 주입 시 테스트용 mock."""
    prompt = JUDGE_PROMPT.format(
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
    return _call(prompt=prompt, system=JUDGE_SYSTEM, schema=LLMJudgment,
                 api_key=api_key, provider=provider, lang=lang, model=model)


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
    """정체 = 피드백 소진(동일 미달차원 반복). 항상 best-so-far(argmax 총점) 반환. Expander 롤백 안 함."""
    cur = history[-1]
    best = max(history, key=lambda r: r.total)
    if cur.grade in ("PASS", "ACCEPTABLE_CAVEAT"):
        return True, "pass", cur
    if len(history) >= MAX_TURNS.get(mode, 2):
        return True, "max_turns → best-so-far soft pass + caveat", best
    if len(history) >= 2 and cur.failed_set == history[-2].failed_set:
        return True, "stall(동일 결손 반복) → best-so-far soft pass", best
    if (len(history) >= 2 and cur.failed_rule_dims
            and cur.failed_rule_dims == history[-2].failed_rule_dims):
        return True, "stall(rule only) → best-so-far soft pass", best
    return False, "continue", cur
