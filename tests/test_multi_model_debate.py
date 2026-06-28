"""multi_model_debate 단위 테스트 — 실LLM 없음 (mock 주입).

synthesis.md 설계안 §테스트 전략 7개 케이스:
1. 실패 내성 매트릭스 (0/1/2/3 생존)
2. 타겟 분리 정합성
3. 불일치 강제 (divergence_verdicts 비어있지 않음)
4. 흡수 추적 정합성
5. 만장일치 조기종료
6. 병렬성 (elapsed 검증)
7. 진행 콜백 순서
"""
from __future__ import annotations

import time
from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.design_schemas import HypothesisOutput, RejectedAlternative
from src.hypothesis.debate_schemas import (
    Critique, DebateResult, DivergencePoint,
    DraftAttempt, ModelRole, SynthesisOutput,
)
from src.hypothesis.multi_model_debate import run_debate, _is_unanimous
from src.hypothesis.scorecard_schemas import DimScore, LLMJudgment, ScorecardResult
from src.schemas import LLMProvider

# ── 픽스처 헬퍼 ────────────────────────────────────────────────────────────────

def _make_hyp(metric: str = "전환율", mechanism: str = "개입→클릭→전환") -> HypothesisOutput:
    return HypothesisOutput(
        raw_idea="test idea",
        jtbd_reframe="전환율 향상",
        implicit_assumptions=["사용자가 CTA를 인지한다"],
        mechanism_path=mechanism,
        confounder_candidates=["계절성"],
        measurability_confirmed=True,
        sharpened_hypothesis=f"CTA 변경 → {metric} 향상",
        suggested_primary_metric=metric,
        suggested_secondary_metrics=[],
        predicted_tradeoff_metrics=[],
        experiment_feasible=True,
        rejected_alternatives=[],
    )


def _make_scorecard(total: int = 88, gate: bool = True) -> ScorecardResult:
    return ScorecardResult(
        scores={},
        total=total,
        gate_passed=gate,
        grade="PASS" if gate and total >= 80 else "ACCEPTABLE_CAVEAT",
    )


def _make_draft(role: ModelRole, metric: str = "전환율", fail: bool = False) -> DraftAttempt:
    if fail:
        return DraftAttempt(role=role, model_id="mock", error="mock error", elapsed_ms=10)
    return DraftAttempt(
        role=role, model_id="mock",
        hypothesis=_make_hyp(metric=metric),
        scorecard=_make_scorecard(),
        elapsed_ms=50,
    )


def _make_synth_output() -> SynthesisOutput:
    return SynthesisOutput(
        final_hypothesis=_make_hyp(metric="전환율"),
        final_scorecard=_make_scorecard(total=92),
        absorbed_from={"sharpened_hypothesis": "claude", "mechanism_path": "gpt"},
        rejected_with_reason={"gemini 지표": "측정 불가"},
        divergence_verdicts=[
            DivergencePoint(
                axis="primary_metric",
                positions={"claude": "전환율", "gpt": "클릭률", "gemini": "전환율"},
                why_it_matters="클릭률은 실질 가치 미반영",
                verdict="전환율 채택 — 구매 목표와 직결",
            )
        ],
        synthesis_rationale="각 모델의 메커니즘 경로를 결합해 재작성, 문장 복사 없음.",
    )


# ── mock expand/sharpen/judge ─────────────────────────────────────────────────

def _mock_expand(idea, **kwargs):
    from src.hypothesis.expander import ExpanderOutput
    return ExpanderOutput(
        jtbd_reframe="전환율 향상",
        implicit_assumptions=["사용자가 CTA를 인지한다"],
        candidate_hypotheses=["CTA 변경 → 전환율 향상"],
    )


_METRICS_CYCLE = ["전환율", "클릭률", "체류시간"]
_metric_counter: dict[str, int] = {}


def _mock_sharpen_diverse(idea, exp, **kwargs):
    """호출마다 다른 지표를 반환해 만장일치 조기종료를 방지."""
    n = _metric_counter.get("n", 0)
    _metric_counter["n"] = n + 1
    return _make_hyp(metric=_METRICS_CYCLE[n % 3])


def _mock_judge(hyp, **kwargs):
    return LLMJudgment(
        falsifiable="Y",
        falsify_scenario="p>0.05이면 기각",
        mechanism_plausible="Y",
        mechanism_gap="",
        clarity="Y",
        clarity_issue="",
    )


def _mock_critique(critic, target, all_survivors, provider, api_key, model):
    return Critique(
        critic_role=critic.role,
        target_role=target.role,
        strengths=["메커니즘이 더 명확함"],
        weaknesses=["지표 '클릭률'은 D1 측정가능성 약함 — 행동이 아닌 중간지표"],
        steal_worthy=["mechanism_path"],
        fatal_flaw=None,
    )


def _mock_synthesize(idea, drafts, critiques):
    return _make_synth_output()


def _run(idea="test", _cred=None, _expand=None, _sharpen=None,
         _judge=None, _critique=None, _synthesize=None, on_progress=None,
         diverse=True):
    """공통 run_debate 래퍼 — 기본값으로 mock 주입.
    diverse=True(기본): 각 모델이 다른 지표 반환 → 만장일치 조기종료 방지.
    diverse=False: 동일 지표 반환 → 만장일치 테스트용.
    """
    def _noop_cred(k):
        return "mock_key"

    if _sharpen is None:
        if diverse:
            _metric_counter.clear()  # 호출 카운터 초기화
            _sharpen = _mock_sharpen_diverse
        else:
            _sharpen = lambda idea, exp, **kw: _make_hyp(metric="전환율", mechanism="개입→클릭→전환")

    return run_debate(
        idea,
        primary_provider=LLMProvider.CLAUDE_CODE,
        primary_key="mock_token",
        lang="ko",
        on_progress=on_progress,
        _expand=_expand or _mock_expand,
        _sharpen=_sharpen,
        _judge=_judge or _mock_judge,
        _critique=_critique or _mock_critique,
        _synthesize=_synthesize or _mock_synthesize,
        _cred=_cred or _noop_cred,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. 실패 내성 매트릭스
# ══════════════════════════════════════════════════════════════════════════════

class TestFailureResilience:

    def test_all_fail_raises(self):
        """0개 생존 → RuntimeError."""
        def _fail_sharpen(idea, exp, **kwargs):
            raise RuntimeError("mock fail")

        with pytest.raises(RuntimeError, match="모든 모델 실패"):
            _run(_sharpen=_fail_sharpen)

    def test_one_survivor_solo_passthrough(self):
        """1개 생존 → degraded=True, 토론 없이 solo 정제."""
        call_count = {"n": 0}

        def _sometimes_fail(idea, exp, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _make_hyp()   # 첫 번째만 성공
            raise RuntimeError("mock fail")

        result = _run(_sharpen=_sometimes_fail)

        assert result.degraded is True
        assert result.survived_count == 1
        assert result.critiques == []
        assert result.winning_hypothesis is not None

    def test_two_survivors_normal_debate(self):
        """2개 생존 → degraded=True, 교차 비평은 2×1=2개."""
        call_count = {"n": 0}
        metrics = ["전환율", "클릭률"]  # 2개 다른 지표 → 만장일치 방지

        def _two_survive(idea, exp, **kwargs):
            n = call_count["n"]
            call_count["n"] += 1
            if n == 0:
                return _make_hyp(metric=metrics[0])
            if n == 1:
                raise RuntimeError("mock fail")  # gpt 실패
            return _make_hyp(metric=metrics[1])  # gemini 성공, 다른 지표

        result = _run(_sharpen=_two_survive)

        assert result.survived_count == 2
        assert result.degraded is True
        assert len(result.critiques) == 2  # 2×(2-1)=2

    def test_three_survivors_full_debate(self):
        """3개 생존 → degraded=False, 비평 6개(3×2)."""
        result = _run()

        assert result.survived_count == 3
        assert result.degraded is False
        assert len(result.drafts) == 3
        assert len(result.critiques) == 6  # 3×(3-1)=6


# ══════════════════════════════════════════════════════════════════════════════
# 2. 타겟 분리 정합성
# ══════════════════════════════════════════════════════════════════════════════

class TestCritiqueTargetSeparation:

    def test_critiques_are_target_separated(self):
        """각 비평이 (critic_role, target_role) 쌍으로 분리됐는지 — 복사 버그 방지."""
        result = _run()
        pairs = [(c.critic_role, c.target_role) for c in result.critiques]
        # 모든 쌍이 유일해야 함
        assert len(pairs) == len(set(pairs))

    def test_no_self_critique(self):
        """critic == target인 비평이 없어야 함."""
        result = _run()
        for c in result.critiques:
            assert c.critic_role != c.target_role

    def test_all_role_combinations_covered(self):
        """3모델 풀 생존 시 모든 (critic, target) 조합이 존재."""
        result = _run()
        roles = [ModelRole.CLAUDE, ModelRole.GPT, ModelRole.GEMINI]
        expected = {(c, t) for c in roles for t in roles if c != t}
        actual = {(c.critic_role, c.target_role) for c in result.critiques}
        assert expected == actual


# ══════════════════════════════════════════════════════════════════════════════
# 3. 불일치 강제 (divergence_verdicts)
# ══════════════════════════════════════════════════════════════════════════════

class TestDivergenceVerdicts:

    def test_divergence_verdicts_not_empty(self):
        """합성 결과에 divergence_verdicts가 비어있지 않아야 함."""
        result = _run()
        assert len(result.synthesis.divergence_verdicts) >= 1

    def test_divergence_has_required_fields(self):
        """각 DivergencePoint에 axis·positions·why_it_matters·verdict 있어야 함."""
        result = _run()
        for dv in result.synthesis.divergence_verdicts:
            assert dv.axis
            assert dv.positions
            assert dv.why_it_matters
            assert dv.verdict

    def test_synthesis_rationale_not_empty(self):
        """짜깁기가 아닌 이유(synthesis_rationale)가 비어있지 않아야 함."""
        result = _run()
        assert result.synthesis.synthesis_rationale.strip()


# ══════════════════════════════════════════════════════════════════════════════
# 4. 흡수 추적 정합성
# ══════════════════════════════════════════════════════════════════════════════

class TestAbsorbedFrom:

    def test_absorbed_from_references_valid_roles(self):
        """absorbed_from 값이 실제 생존한 모델 role 중 하나여야 함."""
        result = _run()
        valid_roles = {d.role.value for d in result.drafts if d.hypothesis}
        for field, role_val in result.synthesis.absorbed_from.items():
            assert role_val in valid_roles, (
                f"absorbed_from['{field}'] = '{role_val}'는 생존 모델에 없음"
            )

    def test_absorbed_from_references_multiple_models(self):
        """최소 2개 이상 모델에서 흡수해야 '진짜 합성'."""
        result = _run()
        if result.survived_count >= 2:
            sources = set(result.synthesis.absorbed_from.values())
            assert len(sources) >= 2, "단일 모델에서만 흡수 — 짜깁기 의심"


# ══════════════════════════════════════════════════════════════════════════════
# 5. 만장일치 조기종료
# ══════════════════════════════════════════════════════════════════════════════

class TestEarlyExitUnanimous:

    def test_unanimous_triggers_early_exit(self):
        """세 안의 지표·메커니즘이 동일하면 early_exit_unanimous=True."""
        result = _run(diverse=False)
        assert result.early_exit_unanimous is True

    def test_unanimous_skips_phase2(self):
        """만장일치 시 Phase2 비평이 없어야 함."""
        result = _run(diverse=False)
        assert result.critiques == []

    def test_diverse_no_early_exit(self):
        """지표가 다르면 early_exit_unanimous=False."""
        result = _run(diverse=True)
        assert result.early_exit_unanimous is False


# ══════════════════════════════════════════════════════════════════════════════
# 6. 병렬성 (Phase 1이 순차가 아님을 시간으로 검증)
# ══════════════════════════════════════════════════════════════════════════════

class TestParallelism:

    def test_phase1_runs_in_parallel(self):
        """3개 모델 각각 sleep(0.3s) → 순차라면 0.9s+, 병렬이면 ~0.3s."""
        DELAY = 0.3

        def _slow_sharpen(idea, exp, **kwargs):
            time.sleep(DELAY)
            return _make_hyp()

        t0 = time.monotonic()
        _run(_sharpen=_slow_sharpen)
        elapsed = time.monotonic() - t0

        # 순차 하한(0.9s)보다 충분히 짧아야 함
        assert elapsed < DELAY * 2.5, (
            f"Phase1이 순차로 실행됐을 가능성: elapsed={elapsed:.2f}s "
            f"(기대 < {DELAY * 2.5:.1f}s)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 7. 진행 콜백 순서
# ══════════════════════════════════════════════════════════════════════════════

class TestProgressCallback:

    def test_progress_messages_include_phases(self):
        """on_progress가 Phase1/2/3 관련 메시지를 순서대로 받아야 함."""
        messages: list[str] = []
        _run(on_progress=messages.append, diverse=True)

        combined = " ".join(messages)
        assert "Phase 1" in combined
        # Phase 2/3는 diverse=True(토론 발생) 시에만 보장
        assert "Phase 2" in combined
        assert "Phase 3" in combined

    def test_progress_called_multiple_times(self):
        """on_progress가 최소 5회 이상 호출돼야 함."""
        calls: list[str] = []
        _run(on_progress=calls.append, diverse=True)
        assert len(calls) >= 5


# ══════════════════════════════════════════════════════════════════════════════
# 유틸: _is_unanimous
# ══════════════════════════════════════════════════════════════════════════════

class TestIsUnanimous:

    def test_same_metric_and_mechanism_is_unanimous(self):
        d1 = _make_draft(ModelRole.CLAUDE, metric="전환율")
        d2 = _make_draft(ModelRole.GPT,    metric="전환율")
        d3 = _make_draft(ModelRole.GEMINI, metric="전환율")
        assert _is_unanimous([d1, d2, d3]) is True

    def test_different_metric_not_unanimous(self):
        d1 = _make_draft(ModelRole.CLAUDE, metric="전환율")
        d2 = _make_draft(ModelRole.GPT,    metric="클릭률")
        d3 = _make_draft(ModelRole.GEMINI, metric="전환율")
        assert _is_unanimous([d1, d2, d3]) is False

    def test_single_draft_not_unanimous(self):
        d1 = _make_draft(ModelRole.CLAUDE)
        assert _is_unanimous([d1]) is False
