"""다양 가설 생성 (멀티-롤 · 하이브리드 멀티프로바이더) 테스트.

expand/sharpen/judge는 주입 mock, score_hypothesis는 실제(결정론) 실행.
"""
from src.hypothesis.diverse_generator import (
    ROLES, available_providers, generate_diverse,
)
from src.hypothesis.expander import ExpanderOutput
from src.schemas import LLMProvider
from tests.test_quality_scorecard import mk_hyp, mk_judge


def _exp(idea, **k):
    return ExpanderOutput(jtbd_reframe="x", implicit_assumptions=[], candidate_hypotheses=["a", "b", "c"])


def _judge_good(*a, **k):
    return mk_judge()


# ── 자격증명 발견 (하이브리드 판단) ───────────────────────────────────
def test_available_providers_primary_first_and_extras():
    creds = {"OPENROUTER_API_KEY": "or-key", "ANTHROPIC_API_KEY": None}
    provs = available_providers(LLMProvider.CLAUDE_CODE, "cc-key", _cred=lambda n: creds.get(n))
    assert provs[0] == (LLMProvider.CLAUDE_CODE, "cc-key")     # primary 맨 앞
    assert (LLMProvider.OPENROUTER, "or-key") in provs
    assert all(p != LLMProvider.ANTHROPIC for p, _ in provs)   # 키 없음 → 제외


def test_available_providers_single_when_no_extras():
    provs = available_providers(LLMProvider.CLAUDE_CODE, "cc-key", _cred=lambda n: None)
    assert provs == [(LLMProvider.CLAUDE_CODE, "cc-key")]


# ── 롤별 생성 ─────────────────────────────────────────────────────────
def test_generates_one_candidate_per_role():
    r = generate_diverse("아이디어", providers=[(LLMProvider.CLAUDE_CODE, "k")],
                         _expand=_exp, _sharpen=lambda *a, **k: mk_hyp(), _judge=_judge_good)
    assert len(r.candidates) == len(ROLES)
    assert {c.role for c in r.candidates} == {role.key for role in ROLES}
    assert r.multi_provider is False


def test_role_context_injected_into_generation():
    captured = []

    def ex(idea, **k):
        captured.append(k.get("domain"))
        return _exp(idea)

    generate_diverse("아이디어", providers=[(LLMProvider.CLAUDE_CODE, "k")],
                     _expand=ex, _sharpen=lambda *a, **k: mk_hyp(), _judge=_judge_good)
    joined = "\n".join(captured)
    assert "공격적 성장" in joined and "역발상" in joined   # 롤 관점이 생성에 주입


# ── 랭킹 (게이트 통과 우선 → 총점) ────────────────────────────────────
def test_ranking_gate_passed_first():
    def sh(idea, exp, **k):
        ctx = k.get("domain", "")
        if "메커니즘" in ctx:
            return mk_hyp()                                   # 게이트 통과
        return mk_hyp(suggested_primary_metric="성공")        # 모호 지표 → 게이트 결격

    r = generate_diverse("아이디어", providers=[(LLMProvider.CLAUDE_CODE, "k")],
                         _expand=_exp, _sharpen=sh, _judge=_judge_good)
    assert r.candidates[0].role == "mechanism"
    assert r.candidates[0].scorecard.gate_passed is True
    assert all(c.scorecard.gate_passed is False for c in r.candidates[1:])


# ── 하이브리드 멀티프로바이더 분산 ────────────────────────────────────
def test_hybrid_distributes_across_providers_round_robin():
    provs = [(LLMProvider.CLAUDE_CODE, "k1"), (LLMProvider.OPENROUTER, "k2")]
    seen = []

    def sh(idea, exp, **k):
        seen.append(k["provider"])
        return mk_hyp()

    r = generate_diverse("아이디어", providers=provs, _expand=_exp, _sharpen=sh, _judge=_judge_good)
    assert r.multi_provider is True
    # 4롤 라운드로빈 → CC, OR, CC, OR
    assert seen == [LLMProvider.CLAUDE_CODE, LLMProvider.OPENROUTER] * 2


# ── 견고성: 한 롤 실패는 배치를 죽이지 않음 ───────────────────────────
def test_failing_role_excluded_not_fatal():
    def sh(idea, exp, **k):
        if "역발상" in k.get("domain", ""):
            raise RuntimeError("boom")
        return mk_hyp()

    r = generate_diverse("아이디어", providers=[(LLMProvider.CLAUDE_CODE, "k")],
                         _expand=_exp, _sharpen=sh, _judge=_judge_good)
    assert "contrarian" in r.roles_failed
    assert len(r.candidates) == len(ROLES) - 1
    assert all(c.role != "contrarian" for c in r.candidates)
