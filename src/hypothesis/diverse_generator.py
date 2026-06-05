"""다양 가설 생성 (멀티-롤 · 하이브리드 멀티프로바이더).

여러 '롤(관점)'로 서로 다른 가설을 발산·정련한 뒤 스코어카드로 선별한다.
- 기본: 선택한 단일 provider에서 롤만 다르게(멀티-롤) → 다양성은 롤에서 나옴.
- 하이브리드: 자격증명이 여러 개면 롤을 provider에 분산(벤더 다양성)까지.

각 후보는 expand→sharpen→judge→score 를 거쳐 게이트통과·총점으로 랭킹.
판정(judge)은 기존 정책대로 provider별 Haiku temp=0 핀(생성만 사용자 모델).
"""
from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from src.config import get_credential
from src.design_schemas import HypothesisOutput
from src.hypothesis.expander import expand
from src.hypothesis.quality_scorecard import judge_hypothesis, score_hypothesis
from src.hypothesis.scorecard_schemas import ScorecardResult
from src.hypothesis.sharpener import sharpen
from src.schemas import LLMProvider


# ── 롤(관점) 정의 — 서로 다른 발산 각도 ──────────────────────────────────────
class Role(BaseModel):
    key: str
    label_ko: str
    label_en: str
    angle_ko: str
    angle_en: str

    def label(self, lang: str) -> str:
        return self.label_ko if lang == "ko" else self.label_en

    def angle(self, lang: str) -> str:
        return self.angle_ko if lang == "ko" else self.angle_en


ROLES: list[Role] = [
    Role(key="growth", label_ko="공격적 성장", label_en="Aggressive growth",
         angle_ko="가장 큰 효과를 노리는 대담한 개입. 업사이드 우선.",
         angle_en="Bold interventions chasing the largest effect; upside-first."),
    Role(key="risk_averse", label_ko="리스크 회피", label_en="Risk-averse",
         angle_ko="부작용·가드레일을 최우선하는 보수적 개입. 다운사이드 최소화.",
         angle_en="Conservative interventions prioritizing guardrails; minimize downside."),
    Role(key="mechanism", label_ko="메커니즘 순수주의", label_en="Mechanism-purist",
         angle_ko="인과 경로가 가장 명확하고 검증 가능한 개입.",
         angle_en="Interventions with the clearest, most testable causal path."),
    Role(key="contrarian", label_ko="역발상", label_en="Contrarian",
         angle_ko="통념과 반대 방향의 가설. 숨은 가정을 뒤집는다.",
         angle_en="Hypotheses against conventional wisdom; flip a hidden assumption."),
]

_PROVIDER_ENV = {
    LLMProvider.CLAUDE_CODE: "CLAUDE_CODE_OAUTH_TOKEN",
    LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
}


def available_providers(
    primary: LLMProvider, primary_key: str,
    _cred: Optional[Callable] = None,
) -> list[tuple[LLMProvider, str]]:
    """자격증명이 있는 (provider, key) 목록. primary를 맨 앞에 둔다(하이브리드 판단용).

    ≥2개면 롤을 벤더에 분산할 수 있다. _cred 주입 시 테스트용.
    """
    cred = _cred or get_credential
    out: list[tuple[LLMProvider, str]] = [(primary, primary_key)]
    for prov, env in _PROVIDER_ENV.items():
        if prov == primary:
            continue
        key = cred(env)
        if key:
            out.append((prov, key))
    return out


def _role_context(role: Role, lang: str, domain: Optional[str]) -> str:
    """롤 관점을 domain 채널로 주입(expand/sharpen이 이미 받는 추가 맥락)."""
    tag = (f"[관점: {role.label(lang)}] {role.angle(lang)}" if lang == "ko"
           else f"[Lens: {role.label(lang)}] {role.angle(lang)}")
    return f"{domain}\n\n{tag}" if domain else tag


class DiverseCandidate(BaseModel):
    role: str
    role_label: str
    provider: str
    hypothesis: HypothesisOutput
    scorecard: ScorecardResult


class DiverseResult(BaseModel):
    candidates: list[DiverseCandidate]   # 랭킹 순(게이트통과 → 총점)
    multi_provider: bool                 # 실제로 둘 이상의 벤더를 사용했는지
    roles_failed: list[str] = []         # 생성 실패해 제외된 롤


def generate_diverse(
    idea: str,
    *,
    providers: list[tuple[LLMProvider, str]],
    lang: str = "ko",
    mode: str = "quick",
    domain: Optional[str] = None,
    roles: Optional[list[Role]] = None,
    model: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
    # 테스트 주입
    _expand: Optional[Callable] = None,
    _sharpen: Optional[Callable] = None,
    _judge: Optional[Callable] = None,
) -> DiverseResult:
    """롤별 가설을 생성·채점해 랭킹. 롤은 providers에 라운드로빈 분산(하이브리드)."""
    roles = roles or ROLES
    expand_fn = _expand or expand
    sharpen_fn = _sharpen or sharpen
    judge_fn = _judge or judge_hypothesis
    emit = on_progress or (lambda n: None)

    cands: list[DiverseCandidate] = []
    failed: list[str] = []
    used: set = set()

    for i, role in enumerate(roles):
        prov, key = providers[i % len(providers)]
        rctx = _role_context(role, lang, domain)
        try:
            exp = expand_fn(idea, api_key=key, provider=prov, lang=lang, model=model, domain=rctx)
            hyp = sharpen_fn(idea, exp, api_key=key, provider=prov, lang=lang,
                             mode=mode, model=model, domain=rctx)
            judgment = judge_fn(hyp, api_key=key, provider=prov, lang=lang)  # judge=Haiku 핀
            sc = score_hypothesis(hyp, judgment, lang=lang)
        except Exception as e:   # 한 롤 실패는 배치를 죽이지 않음
            import logging
            logging.getLogger(__name__).warning("다양생성 롤 '%s' 실패 → 제외: %s", role.key, e)
            failed.append(role.key)
            emit(f"role:{role.key}:failed")
            continue
        used.add(prov)
        cands.append(DiverseCandidate(
            role=role.key, role_label=role.label(lang), provider=prov.value,
            hypothesis=hyp, scorecard=sc,
        ))
        emit(f"role:{role.key}:{sc.grade}({sc.total})")

    # 랭킹: 게이트 통과 우선, 그다음 총점 (스코어카드 _best_idx 정책과 동일)
    cands.sort(key=lambda c: (c.scorecard.gate_passed, c.scorecard.total), reverse=True)
    return DiverseResult(candidates=cands, multi_provider=len(used) > 1, roles_failed=failed)
