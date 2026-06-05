"""
AB Lens - Streamlit 메인 앱
A/B 테스트 결과를 AI가 분석하는 1페이지 브리핑
"""

import streamlit as st
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(__file__))

from src.schemas import ABTestInput, BriefOutput, LLMProvider
from src.agents.statistical import analyze_stats
from src.agents.bias_detector import detect_bias
from src.agents.recommender import recommend
from src.safety import SessionLimiter
from src.i18n import get_texts
from src.config import get_credential
from src.design_schemas import DesignContext
from src.context_loop import build_observed_result, context_loop_guard
from src.hypothesis.pipeline import run_hypothesis_pipeline
from src.hypothesis.quality_loop import run_quality_loop
from src.design.assembler import DesignFacts, assemble_design_context
from src.design.doc_generator import render_design_doc
from src.llm_client import (
    CLAUDE_CODE_MODELS,
    ANTHROPIC_MODELS,
    OPENROUTER_MODELS,
    CLAUDE_CODE_MODEL,
    ANTHROPIC_MODEL,
    OPENROUTER_MODEL,
)

# 페이지 설정
st.set_page_config(
    page_title="AB Lens",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS 스타일
st.markdown(
    """
<style>
.metric-card {
    background-color: #f8f9fa;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    border-left: 4px solid #4CAF50;
}
.bias-card-high {
    background-color: #fff5f5;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    border-left: 4px solid #e53e3e;
}
.bias-card-medium {
    background-color: #fffbeb;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    border-left: 4px solid #d69e2e;
}
.bias-card-low {
    background-color: #f0fff4;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    border-left: 4px solid #38a169;
}
.final-rec {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 12px;
    padding: 24px;
    margin: 16px 0;
}
</style>
""",
    unsafe_allow_html=True,
)


def render_sidebar() -> tuple[str, str, LLMProvider, str]:
    """사이드바 렌더링. (api_key, lang, provider, model) 반환"""
    with st.sidebar:
        # 언어 토글
        if "lang" not in st.session_state:
            st.session_state.lang = "ko"

        lang = st.session_state.lang
        t = get_texts(lang)

        if st.button(t["lang_toggle"]):
            st.session_state.lang = "en" if lang == "ko" else "ko"
            st.rerun()

        st.divider()

        # Provider 선택 (Claude Code 구독 = 비용 0, 기본값)
        cc_label = "Claude Code 구독 (무료)" if lang == "ko" else "Claude Code subscription (free)"
        provider_options = {
            cc_label: LLMProvider.CLAUDE_CODE,
            t["provider_openrouter"]: LLMProvider.OPENROUTER,
            t["provider_anthropic"]: LLMProvider.ANTHROPIC,
        }
        provider_label = st.radio(
            t["provider_select"],
            options=list(provider_options.keys()),
            index=0,
        )
        provider = provider_options[provider_label]

        # provider별 자격증명 환경변수명 + 레이블/플레이스홀더
        cred_env = {
            LLMProvider.CLAUDE_CODE: "CLAUDE_CODE_OAUTH_TOKEN",
            LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
            LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        }[provider]
        placeholder = {
            LLMProvider.CLAUDE_CODE: "sk-ant-oat01-...",
            LLMProvider.OPENROUTER: "sk-or-...",
            LLMProvider.ANTHROPIC: "sk-ant-...",
        }[provider]
        if provider == LLMProvider.CLAUDE_CODE:
            api_key_label = "Claude Code OAuth 토큰" if lang == "ko" else "Claude Code OAuth token"
        elif provider == LLMProvider.ANTHROPIC:
            api_key_label = t["api_key_label_anthropic"]
        else:
            api_key_label = t["api_key_label_openrouter"]

        # ~/.hermes/.env 에서 자동 로드 (있으면 프리필)
        auto_key = get_credential(cred_env) or ""
        api_key = st.text_input(
            api_key_label,
            type="password",
            value=auto_key,
            help=t["sidebar_api_key_help"],
            placeholder=placeholder,
        )
        if auto_key:
            st.caption("✅ 환경(~/.hermes/.env)에서 자동 로드됨" if lang == "ko"
                       else "✅ Auto-loaded from ~/.hermes/.env")

        st.divider()

        # 모델 선택
        model_options = {
            LLMProvider.CLAUDE_CODE: CLAUDE_CODE_MODELS,
            LLMProvider.ANTHROPIC: ANTHROPIC_MODELS,
            LLMProvider.OPENROUTER: OPENROUTER_MODELS,
        }[provider]
        model_defaults = {
            LLMProvider.CLAUDE_CODE: CLAUDE_CODE_MODEL,
            LLMProvider.ANTHROPIC: ANTHROPIC_MODEL,
            LLMProvider.OPENROUTER: OPENROUTER_MODEL,
        }[provider]
        model_label = "모델 선택" if lang == "ko" else "Select model"
        selected_model = st.selectbox(
            model_label,
            options=model_options,
            index=model_options.index(model_defaults),
        )
        model_hint = (
            "생성·구체화에만 적용됩니다. 품질 판정(스코어카드)은 항상 Haiku temp=0으로 고정 — "
            "추론이 필요한 가설 생성은 Sonnet/Opus를 권장."
            if lang == "ko" else
            "Applies to generation/refinement only. Quality judging is always pinned to "
            "Haiku temp=0. Use Sonnet/Opus for reasoning-heavy hypothesis generation."
        )
        st.caption(model_hint)

        st.divider()

        # 요청 카운터 표시
        limiter = SessionLimiter()
        remaining = limiter.remaining_requests
        st.metric(t["remaining_requests"], f"{remaining}/10")

        if remaining < 3:
            st.warning(t["request_limit_warning"])

    return api_key, st.session_state.lang, provider, selected_model


def render_design_tab(api_key: str, lang: str, provider: LLMProvider, model: str | None = None):
    """탭1 — 실험 설계: 아이디어 → 가설 고도화 → 사실수치 → 설계서/json."""
    ko = lang == "ko"
    st.subheader("🧪 실험 설계" if ko else "🧪 Experiment Design")
    st.caption(
        "아이디어를 가설로 고도화하고, 설계 약속(.json)을 만들어 결과 분석에 이월합니다."
        if ko else
        "Refine an idea into a hypothesis and produce a design contract (.json) carried into analysis."
    )

    # ── session_state 초기화 ──────────────────────────────────────────────────
    if "rerun_count" not in st.session_state:
        st.session_state["rerun_count"] = 0
    if "alt_rerun_pending" not in st.session_state:
        st.session_state["alt_rerun_pending"] = False
    if "alt_rerun_idea" not in st.session_state:
        st.session_state["alt_rerun_idea"] = ""
    if "alt_rerun_mode" not in st.session_state:
        st.session_state["alt_rerun_mode"] = "quick"
    if "hyp_result_initial" not in st.session_state:
        st.session_state["hyp_result_initial"] = None
    if "hyp_result_alt" not in st.session_state:
        st.session_state["hyp_result_alt"] = None

    # ── 대안 재실행 트리거 처리 (버튼 클릭 → rerun() 후 이 블록에서 실행) ────
    if st.session_state["alt_rerun_pending"]:
        st.session_state["alt_rerun_pending"] = False
        alt_idea = st.session_state["alt_rerun_idea"]
        alt_mode = st.session_state["alt_rerun_mode"]
        if not api_key:
            st.error("API 키를 입력하세요." if ko else "Please enter an API key.")
        else:
            try:
                with st.status(
                    "대안 가설 재실행 중…" if ko else "Re-running with alternative hypothesis…",
                    expanded=True,
                ) as status:
                    alt_result = run_hypothesis_pipeline(
                        alt_idea,
                        mode=alt_mode,
                        hypothesis_state="team_agreed",
                        api_key=api_key,
                        provider=provider,
                        lang=lang,
                        on_progress=lambda node: status.write(f"✓ {node}"),
                        model=model,
                    )
                    # model이 지정된 경우 전달
                    status.update(label="완료" if ko else "Done", state="complete")
                st.session_state["hyp_result_alt"] = alt_result
                # 설계 컨텍스트 무효화
                st.session_state.pop("design_context", None)
                st.session_state.pop("design_doc_md", None)
            except Exception as e:
                st.error(f"오류: {e}" if ko else f"Error: {e}")

    idea = st.text_area(
        "실험 아이디어" if ko else "Experiment idea",
        value=st.session_state.get("design_idea", ""),
        placeholder="예: 결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오를 것이다",
    )
    c1, c2 = st.columns(2)
    mode = c1.radio(
        "분석 깊이" if ko else "Depth", ["quick", "deep"],
        format_func=lambda m: {"quick": "Quick (~20s, 편향 3종)", "deep": "Deep (~40s, 편향 7종)"}[m],
    )
    state = c2.radio(
        "가설 상태" if ko else "Hypothesis state", ["initial_idea", "team_agreed"],
        format_func=lambda s: {"initial_idea": "초기 아이디어 (발산부터)", "team_agreed": "팀 합의 완료 (발산 스킵)"}[s]
        if ko else {"initial_idea": "Initial idea", "team_agreed": "Team-agreed"}[s],
    )

    use_loop = st.checkbox(
        "멀티턴 고도화 (가설품질 스코어카드 게이트까지 반복)" if ko
        else "Multi-turn refinement (loop until quality scorecard gate)",
        value=st.session_state.get("use_quality_loop", False),
        help="측정·반증 게이트와 6차원 품질을 만족할 때까지 자동 재고도화. Codex·Gemini 룰가이드 판정 사용."
        if ko else "Auto-refine until the measurability/falsifiability gate + 6-dim quality pass.",
    )
    st.session_state["use_quality_loop"] = use_loop

    # ── T2: 도메인 맥락(선택). 멀티턴일 때만 — 비우면 부족 시 질문 ──
    domain_in: dict[str, str] = {}
    if use_loop:
        with st.expander("도메인/서비스 맥락 (선택 — 비우면 부족 시 질문)" if ko
                         else "Domain/service context (optional — asked if missing)"):
            domain_in["service_type"] = st.text_input("서비스/제품 유형" if ko else "Service/product type", key="dom_service_type")
            domain_in["user_segment"] = st.text_input("타겟 사용자" if ko else "Target users", key="dom_user_segment")
            domain_in["primary_goal"] = st.text_input("핵심 비즈니스 목표/지표" if ko else "Primary goal/metric", key="dom_primary_goal")
            domain_in["constraints"] = st.text_input("제약(규제·기술·기간)" if ko else "Constraints", key="dom_constraints")

    def _store(result, used_idea):
        st.session_state.hyp_result = result
        st.session_state.design_idea = used_idea
        st.session_state["hyp_result_initial"] = result
        st.session_state["hyp_result_alt"] = None
        st.session_state["rerun_count"] = 0
        st.session_state.pop("design_context", None)
        st.session_state.pop("design_doc_md", None)

    def _run_loop(used_idea, used_mode, used_state, domain_str):
        with st.status("가설 고도화 중…" if ko else "Refining…", expanded=True) as status:
            result = run_quality_loop(
                used_idea, mode=used_mode, hypothesis_state=used_state,
                api_key=api_key, provider=provider, lang=lang, model=model,
                domain=domain_str or None,
                on_progress=lambda node: status.write(f"✓ {node}"),
            )
            status.update(label="완료" if ko else "Done", state="complete")
        _store(result, used_idea)

    # ── 도메인 질문 대기 상태: 질문 폼 ──
    pend = st.session_state.get("domain_pending")
    if pend:
        from src.hypothesis.domain_intake import DomainContext, DomainQuestion, context_from_answers
        st.info("ℹ️ 도메인 정보가 부족합니다. 답하면 더 정확히 고도화됩니다." if ko
                else "ℹ️ Domain context is thin. Answer for sharper refinement.")
        rnd = pend.get("round", 0)        # 라운드 nonce → 위젯 key 충돌/고스트 답변 방지
        ans = {q["field"]: st.text_input(q["question"], key=f"dq_{rnd}_{i}_{q['field']}")
               for i, q in enumerate(pend["questions"])}
        ca, cb = st.columns(2)
        go = ca.button("답변 반영하고 고도화" if ko else "Refine with answers", type="primary")
        skip = cb.button("질문 건너뛰고 진행" if ko else "Skip & proceed")
        if go or skip:
            base = DomainContext(**pend["inferred"])
            ctx = base if skip else context_from_answers(
                [DomainQuestion(**q) for q in pend["questions"]], ans, base=base)
            st.session_state.pop("domain_pending", None)   # 항상 정리 — 실패해도 폼에 갇히지 않게
            try:
                _run_loop(pend["idea"], pend["mode"], pend["state"], ctx.to_prompt(lang))
            except Exception as e:
                st.error(f"오류: {e}" if ko else f"Error: {e}")
                return
            st.rerun()
        return

    if st.button("가설 고도화" if ko else "Refine hypothesis", type="primary"):
        if not api_key:
            st.error("API 키를 입력하세요." if ko else "Please enter an API key.")
            return
        if not idea.strip():
            st.error("아이디어를 입력하세요." if ko else "Please enter an idea.")
            return
        if use_loop:
            from src.hypothesis.domain_intake import DomainContext, analyze_domain
            existing = DomainContext(**domain_in)
            try:
                with st.spinner("도메인 점검 중…" if ko else "Checking domain…"):
                    intake = analyze_domain(idea, existing, api_key=api_key, provider=provider, lang=lang, model=model)
            except Exception as e:
                st.error(f"오류: {e}" if ko else f"Error: {e}")
                return
            merged = existing.merged_with(intake.inferred)   # 사용자 입력 우선, 빈 칸은 추론으로
            # 병합 후에도 비어있는 필드에 대한 질문만 남김 (이미 답한 건 안 물음)
            ask_fields = merged.missing_fields() | {"other"}
            qs = [q for q in intake.questions if q.field in ask_fields]
            if (not intake.sufficient) and qs:
                rnd = st.session_state.get("domain_round", 0) + 1
                st.session_state["domain_round"] = rnd
                st.session_state["domain_pending"] = {
                    "idea": idea, "mode": mode, "state": state,
                    "questions": [q.model_dump() for q in qs],
                    "inferred": merged.model_dump(),     # 병합본을 답변 base로
                    "round": rnd,
                }
                st.rerun()
            else:
                try:
                    _run_loop(idea, mode, state, merged.to_prompt(lang))
                except Exception as e:
                    st.error(f"오류: {e}" if ko else f"Error: {e}")
                    return
        else:
            try:
                with st.status("가설 고도화 중…" if ko else "Refining…", expanded=True) as status:
                    result = run_hypothesis_pipeline(
                        idea, mode=mode, hypothesis_state=state,
                        api_key=api_key, provider=provider, lang=lang,
                        on_progress=lambda node: status.write(f"✓ {node}"), model=model,
                    )
                    status.update(label="완료" if ko else "Done", state="complete")
                _store(result, idea)
            except Exception as e:
                st.error(f"오류: {e}" if ko else f"Error: {e}")
                return

    # ── 표시할 결과 결정 (대안 재실행 결과 우선, 없으면 최초 결과) ────────────
    alt_result = st.session_state.get("hyp_result_alt")
    is_alt_run = alt_result is not None
    result = alt_result if is_alt_run else st.session_state.get("hyp_result")

    if not result:
        return

    if result.trivial:
        st.warning(f"🛑 {result.trivial_reason}")
        st.info("A/B 테스트 대상이 아닙니다. 그냥 적용하세요 (Just Do It)." if ko else
                "Not an A/B test candidate. Just do it.")
        return

    hyp = result.hypothesis

    # ── 멀티턴 루프 결과: 가설품질 스코어카드 요약 (run_quality_loop일 때만) ──
    sc = getattr(result, "scorecard", None)
    if sc is not None:
        # 내부 enum → 사용자 친화 라벨 (로직/스키마는 enum 유지)
        GRADE = {
            "PASS": ("✅ 통과 — 실험 진행 가능", "✅ Pass — ready to run"),
            "ACCEPTABLE_CAVEAT": ("🟡 조건부 통과 — 보완점 있으나 진행 가능", "🟡 Acceptable — minor gaps, can proceed"),
            "REFINE": ("🔁 보강 필요 — 더 다듬어야 함", "🔁 Needs work — refine further"),
            "REDESIGN": ("🔴 재설계 필요 — 측정/반증 불가", "🔴 Redesign — not measurable/falsifiable"),
        }
        DIM = {"ko": {"D1": "측정가능성", "D2": "반증가능성", "D3": "인과메커니즘",
                      "D4": "정렬·리스크", "D5": "대안탐색", "D6": "명료성"},
               "en": {"D1": "Measurable", "D2": "Falsifiable", "D3": "Mechanism",
                      "D4": "Align·Risk", "D5": "Alternatives", "D6": "Clarity"}}[lang if lang in ("ko", "en") else "ko"]

        def _stop(r: str) -> str:
            if "REDESIGN" in r or "결격" in r:
                return "측정·반증 게이트 미충족" if ko else "gate not met"
            if "max_turns" in r or "hard_limit" in r:
                return "최대 반복 도달 — 최선안 채택" if ko else "max rounds — best kept"
            if "stall" in r:
                return "더 개선되지 않음 — 최선안 채택" if ko else "no further improvement — best kept"
            if r == "pass":
                return "품질 통과" if ko else "passed"
            return r

        turns = getattr(result, "turns", 1)
        best_turn = getattr(result, "best_turn", 1)
        glabel = GRADE.get(sc.grade, (sc.grade, sc.grade))[0 if ko else 1]
        st.markdown(f"#### {glabel}")
        st.caption((f"{turns}회 고도화 (채택 {best_turn}회차) · 게이트(측정·반증) {'충족' if sc.gate_passed else '미충족'} · "
                    f"품질점수 {sc.total}/100 · {_stop(result.stop_reason)}") if ko
                   else f"{turns} rounds (picked #{best_turn}) · gate {'met' if sc.gate_passed else 'unmet'} · "
                        f"score {sc.total}/100 · {_stop(result.stop_reason)}")
        if sc.scores:
            for col, (d, ds) in zip(st.columns(len(sc.scores)), sc.scores.items()):
                delta = ("충족" if ds.passed else "미달") if ko else ("ok" if ds.passed else "low")
                col.metric(DIM.get(d, d), f"{ds.score}/{ds.max}", delta,
                           delta_color="normal" if ds.passed else "inverse")
        if sc.caveats:
            named = []
            for c in sc.caveats:
                key, _, rest = c.partition(":")
                named.append(f"{DIM.get(key.strip(), key.strip())}:{rest}" if rest else c)
            st.warning(("⚠️ 보완점 — " if ko else "⚠️ Caveats — ") + " / ".join(named))
        with st.expander((f"고도화 과정 ({turns}회)") if ko else f"Refinement history ({turns})"):
            for h in getattr(result, "history", []):
                mark = "⭐" if h.turn == best_turn else "▫️"
                hg = GRADE.get(h.grade, (h.grade, h.grade))[0 if ko else 1]
                gaps = ", ".join(DIM.get(x, x) for x in h.failed_set)
                st.write(f"{mark} {h.turn}{'회차' if ko else ''}: {hg} · {'품질' if ko else 'score'} {h.total}"
                         + (f" · {'미보완' if ko else 'gaps'} {gaps}" if gaps else ""))
        st.divider()

    # 대안 재실행 배지
    if is_alt_run:
        st.info("🔄 **(대안 선택 재실행)**" if ko else "🔄 **(Alternative re-run)**")

    st.markdown(f"### {'고도화된 가설' if ko else 'Sharpened hypothesis'}")
    st.success(hyp.sharpened_hypothesis)
    st.markdown(f"**{'메커니즘' if ko else 'Mechanism'}**: {hyp.mechanism_path}")
    with st.expander("암묵적 전제 / 혼란변수 / 기각 대안" if ko else "Assumptions / confounders / rejected"):
        st.markdown("**암묵적 전제**")
        for a in hyp.implicit_assumptions:
            st.markdown(f"- {a}")
        st.markdown("**혼란변수 후보**")
        for c in hyp.confounder_candidates:
            st.markdown(f"- {c}")
        st.markdown("**기각된 대안 (Decision Log)**")
        for r in hyp.rejected_alternatives:
            st.markdown(f"- ~~{r.hypothesis}~~ — {r.rejection_reason}")

    if result.bias_screen and result.bias_screen.biases:
        active = [b for b in result.bias_screen.biases if b.status == "active"]
        if active:
            st.markdown("#### ⚠️ 설계 편향 경고 (차단 아님)" if ko else "#### ⚠️ Design bias warnings")
            for b in active:
                st.warning(f"**{b.bias_type}**: {b.evidence} → {b.counter_measure}")

    # ── 기각된 대안 — 재실행 UI ───────────────────────────────────────────────
    # 최초 실행 결과의 rejected_alternatives를 기준으로 표시
    initial_result = st.session_state.get("hyp_result_initial") or result
    initial_hyp = initial_result.hypothesis if initial_result else None
    rejected = initial_hyp.rejected_alternatives if initial_hyp else []

    if rejected:
        st.divider()
        rerun_count = st.session_state.get("rerun_count", 0)
        limit_reached = rerun_count >= 1

        with st.expander(
            "💡 기각된 대안 — 선택하면 이 가설로 재실행합니다"
            if ko else
            "💡 Rejected alternatives — click to re-run with this hypothesis",
            expanded=not is_alt_run,
        ):
            if limit_reached:
                st.warning(
                    "⚠️ 대안 탐색은 1회까지 가능합니다." if ko
                    else "⚠️ Alternative exploration is limited to 1 re-run."
                )

            for idx, r in enumerate(rejected):
                with st.container():
                    st.markdown(f"**가설**: {r.hypothesis}")
                    st.caption(f"기각 이유: {r.rejection_reason}")
                    btn_label = (
                        "🔄 이 가설로 재실행" if ko else "🔄 Re-run with this hypothesis"
                    )
                    if st.button(
                        btn_label,
                        key=f"alt_rerun_btn_{idx}",
                        disabled=limit_reached,
                    ):
                        st.session_state["rerun_count"] = rerun_count + 1
                        st.session_state["alt_rerun_pending"] = True
                        st.session_state["alt_rerun_idea"] = r.hypothesis
                        st.session_state["alt_rerun_mode"] = mode
                        st.rerun()
                    st.markdown("---")

        # 최초 실행 결과의 Decision Log (대안 재실행 후에도 항상 표시)
        if is_alt_run and initial_hyp and initial_hyp.rejected_alternatives:
            with st.expander(
                "📋 최초 실행 기각 대안 Decision Log" if ko
                else "📋 Initial run rejected alternatives Decision Log",
                expanded=False,
            ):
                for r in initial_hyp.rejected_alternatives:
                    st.markdown(f"- ~~{r.hypothesis}~~ — {r.rejection_reason}")

    st.divider()
    st.markdown(f"### {'사실 수치 입력' if ko else 'Factual inputs'} "
                f"({'LLM이 만들지 않음' if ko else 'never invented by LLM'})")
    st.caption(f"제안된 1차 지표: **{hyp.suggested_primary_metric}**")

    f1, f2, f3 = st.columns(3)
    metric_type = f1.selectbox("지표 타입", ["proportion", "continuous", "count"])
    baseline = f1.number_input("baseline", value=0.10, format="%.4f")
    rand = f1.selectbox("랜덤화 단위", ["user", "session", "device", "cluster"])
    agreed_mde = f2.number_input("합의 MDE", value=0.05, format="%.4f")
    std_dev_in = f2.number_input("표준편차 (continuous만)", value=0.0, format="%.4f")
    duration = f2.number_input("실험 기간(일)", value=14, min_value=1, step=1)
    alpha = f3.number_input("alpha", value=0.05, format="%.3f")
    power = f3.number_input("power", value=0.80, format="%.2f")
    icc_in = f3.number_input("ICC (cluster만)", value=0.0, format="%.4f")
    stop = st.text_input("중단 기준 (peeking 방지)", value="목표 표본 도달 시 종료, 중간 peeking 금지")

    if st.button("설계 확정 → 설계서 생성" if ko else "Finalize → generate design doc"):
        try:
            facts = DesignFacts(
                metric_type=metric_type, baseline=baseline, agreed_mde=agreed_mde,
                std_dev=std_dev_in if std_dev_in > 0 else None,
                alpha=alpha, power=power, randomization_unit=rand,
                experiment_duration_days=int(duration),
                icc=icc_in if icc_in > 0 else None, stop_criteria=stop,
            )
            ctx = assemble_design_context(hyp, result.bias_screen, facts)
            st.session_state.design_context = ctx
            st.session_state.design_doc_md = render_design_doc(ctx, hyp)
        except Exception as e:
            st.error(f"설계 생성 오류: {e}" if ko else f"Design error: {e}")

    ctx = st.session_state.get("design_context")
    if ctx:
        st.success(
            f"설계 확정 — 필요 표본 {ctx.target_sample_size:,}명, "
            f"품질 {ctx.design_quality.advisory_score}/100"
            if ko else
            f"Finalized — sample {ctx.target_sample_size:,}, quality {ctx.design_quality.advisory_score}/100"
        )
        with st.expander("📄 설계서 미리보기" if ko else "📄 Design doc preview", expanded=True):
            st.markdown(st.session_state.design_doc_md)
        d1, d2 = st.columns(2)
        d1.download_button(
            "📄 설계서(.md)", st.session_state.design_doc_md,
            file_name="experiment-design.md", mime="text/markdown",
        )
        d2.download_button(
            "🔒 ab-design-context.json", ctx.to_json(),
            file_name="ab-design-context.json", mime="application/json",
        )
        st.caption("→ 결과 분석 탭에서 이 설계가 자동 적용됩니다 (Context Loop)."
                   if ko else "→ Auto-applied in the analysis tab (Context Loop).")


def render_context_uploader(lang: str) -> DesignContext | None:
    """탭1에서 받은 ab-design-context.json 업로드 (선택). Context Loop 입력."""
    label = (
        "🔒 설계 컨텍스트(.json) 업로드 — 설계 때의 약속과 대조 (선택)"
        if lang == "ko"
        else "🔒 Upload design context (.json) — check against your pre-registered plan (optional)"
    )
    up = st.file_uploader(label, type=["json"], key="ctx_upload")
    if up is None:
        return None
    try:
        ctx = DesignContext.from_json(up.read())
    except ValueError as e:
        msg = "설계 컨텍스트를 읽지 못했습니다" if lang == "ko" else "Could not read design context"
        st.warning(f"{msg}: {e}")
        return None
    loaded = "설계 컨텍스트 로드됨" if lang == "ko" else "Design context loaded"
    st.caption(f"✅ {loaded}: {ctx.sharpened_hypothesis[:50]}…")
    return ctx


def render_context_loop(violations: list, lang: str):
    """Context Loop 위반 배지 (탭2 최상단). 약속 위반 시 강조."""
    if not violations:
        return
    title = (
        "🔒 Context Loop — 설계 약속 위반 감지"
        if lang == "ko"
        else "🔒 Context Loop — design-plan violations detected"
    )
    st.subheader(title)
    for v in violations:
        if v.severity == "high":
            st.error(f"🔴 {v.message}")
        else:
            st.warning(f"⚠️ {v.message}")
    st.divider()


def render_input_form(t: dict, limiter: SessionLimiter) -> ABTestInput | None:
    """입력 폼 렌더링. 제출 시 ABTestInput 반환"""
    st.subheader(t["required_fields"])

    col1, col2 = st.columns(2)

    with col1:
        metric_name = st.text_input(
            t["metric_name"],
            placeholder="예: 전환율, CTR, ARPU",
            value="전환율",
        )
        treatment_value = st.number_input(
            t["treatment_value"],
            min_value=0.0,
            max_value=1.0,
            value=0.12,
            step=0.001,
            format="%.4f",
        )
        control_value = st.number_input(
            t["control_value"],
            min_value=0.0,
            max_value=1.0,
            value=0.10,
            step=0.001,
            format="%.4f",
        )
        p_value = st.number_input(
            t["p_value"],
            min_value=0.0,
            max_value=1.0,
            value=0.03,
            step=0.001,
            format="%.4f",
        )

    with col2:
        sample_size_treatment = st.number_input(
            t["sample_size_treatment"],
            min_value=1,
            value=5000,
            step=100,
        )
        sample_size_control = st.number_input(
            t["sample_size_control"],
            min_value=1,
            value=5000,
            step=100,
        )
        experiment_days = st.number_input(
            t["experiment_days"],
            min_value=1,
            value=14,
            step=1,
        )

    st.subheader(t["optional_fields"])

    col3, col4 = st.columns(2)

    with col3:
        dev_cost_weeks = st.number_input(
            t["dev_cost"],
            min_value=0.0,
            value=0.0,
            step=0.5,
            format="%.1f",
        )
        priority_options = {
            "": None,
            t.get("priority_high", "높음"): "high",
            t.get("priority_medium", "중간"): "medium",
            t.get("priority_low", "낮음"): "low",
        }
        priority_label = st.selectbox(
            t["business_priority"],
            options=list(priority_options.keys()),
        )
        business_priority = priority_options.get(priority_label)

        is_random_assignment = st.checkbox(t["is_random"], value=True)
        multiple_metrics = st.checkbox(t["multiple_metrics"], value=False)

    with col4:
        prior_expectation = st.text_input(
            t["prior_expectation"],
            placeholder="예: 버튼 색상 변경으로 5% 향상 기대",
        )
        business_context = st.text_area(
            t["business_context"],
            placeholder="실험 배경, 목적, 제약 조건 등",
            height=120,
        )

    # 분석 버튼
    if st.button(t["analyze_btn"], type="primary", use_container_width=True):
        if not metric_name:
            st.error("메트릭 이름을 입력해주세요." if st.session_state.lang == "ko" else "Please enter a metric name.")
            return None

        # 입력 길이 제한 적용
        if business_context:
            business_context = limiter.validate_input(business_context)
        if prior_expectation:
            prior_expectation = limiter.validate_input(prior_expectation)

        return ABTestInput(
            metric_name=metric_name,
            treatment_value=treatment_value,
            control_value=control_value,
            p_value=p_value,
            sample_size_treatment=int(sample_size_treatment),
            sample_size_control=int(sample_size_control),
            experiment_days=int(experiment_days),
            dev_cost_weeks=dev_cost_weeks if dev_cost_weeks > 0 else None,
            business_priority=business_priority,
            prior_expectation=prior_expectation if prior_expectation else None,
            is_random_assignment=is_random_assignment,
            multiple_metrics=multiple_metrics,
            business_context=business_context if business_context else None,
        )

    return None


def render_stats(stats, t: dict):
    """통계 분석 섹션 렌더링"""
    st.subheader(t["section_stats"])

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        effect_color = "normal" if stats.effect_size_pp > 0 else "inverse"
        st.metric(
            t["effect_size_pp"],
            f"{stats.effect_size_pp:+.2f}pp",
            delta=f"{stats.effect_size_relative_pct:+.1f}%",
            delta_color=effect_color,
        )

    with col2:
        st.metric(
            "P-Value",
            f"{stats.effect_size_pp:.4f}" if False else f"p={0.0:.4f}",  # 실제 p_value는 입력에서
            label_visibility="visible",
        )
        sig_label = t["significant"] if stats.is_significant else t["not_significant"]
        st.caption(sig_label)

    with col3:
        power_color = "normal" if stats.power_pct >= 80 else "inverse"
        st.metric(
            t["power"],
            f"{stats.power_pct:.1f}%",
            delta_color=power_color,
        )

    with col4:
        srm_label = t["srm_detected"] if stats.srm_detected else t["srm_ok"]
        st.metric(t["srm_status"], srm_label)

    if stats.srm_detail:
        st.warning(f"⚠️ {stats.srm_detail}")

    if stats.additional_sample_needed:
        st.info(f"📊 {t['additional_sample']}: {stats.additional_sample_needed:,}")

    with st.expander(t["interpretation"]):
        st.code(stats.interpretation)


def render_bias(bias_report, t: dict):
    """편향 감지 섹션 렌더링"""
    st.subheader(t["section_bias"])

    risk_map = {"high": t["risk_high"], "medium": t["risk_medium"], "low": t["risk_low"]}
    overall_label = risk_map.get(bias_report.overall_risk, bias_report.overall_risk)
    st.markdown(f"**{t['overall_risk']}**: {overall_label}")

    for bias_item in bias_report.biases:
        card_class = f"bias-card-{bias_item.severity}"
        severity_label = {
            "high": t["bias_severity_high"],
            "medium": t["bias_severity_medium"],
            "low": t["bias_severity_low"],
        }.get(bias_item.severity, bias_item.severity)

        st.markdown(
            f"""<div class="{card_class}">
<strong>{bias_item.name}</strong> &nbsp; {severity_label}<br/>
<p>{bias_item.description}</p>
<small>💡 <strong>{t['counter_measure']}</strong>: {bias_item.counter}</small>
{"<br/><small>📄 " + t['paper_ref'] + ": " + bias_item.paper_reference + "</small>" if bias_item.paper_reference else ""}
</div>""",
            unsafe_allow_html=True,
        )


def render_causal(causal_alt, t: dict):
    """인과추론 섹션 렌더링"""
    if not causal_alt:
        return

    st.subheader(t["section_causal"])

    if causal_alt.experiment_feasible:
        st.success(t["causal_feasible"])
    else:
        st.error(t["causal_not_feasible"])
        if causal_alt.alternative_method:
            st.markdown(f"**{t['alternative_method']}**: {causal_alt.alternative_method}")
        if causal_alt.method_description:
            st.info(causal_alt.method_description)


def render_recommendation(rec, t: dict):
    """추천 섹션 렌더링"""
    st.subheader(t["section_recommend"])

    # 시나리오 카드
    cols = st.columns(len(rec.scenarios))
    for i, scenario in enumerate(rec.scenarios):
        with cols[i]:
            risk_label = {
                "high": t["risk_high"],
                "medium": t["risk_medium"],
                "low": t["risk_low"],
            }.get(scenario.risk_level, scenario.risk_level)

            st.markdown(f"### {scenario.name}")
            st.markdown(f"**확률**: {scenario.probability_pct}%")
            st.markdown(f"**위험도**: {risk_label}")

            st.markdown(f"**{t['scenario_pros']}**")
            for pro in scenario.pros:
                st.markdown(f"✅ {pro}")

            st.markdown(f"**{t['scenario_cons']}**")
            for con in scenario.cons:
                st.markdown(f"❌ {con}")

    st.divider()

    # 최종 추천 하이라이트
    st.markdown(
        f"""<div class="final-rec">
<h3>🎯 {t['final_recommendation']}</h3>
<p style="font-size: 1.1em;">{rec.final_recommendation}</p>
<hr style="border-color: rgba(255,255,255,0.3)"/>
<p><strong>{t['confidence']}</strong>: {rec.confidence_pct}%</p>
<p><strong>{t['rationale']}</strong>: {rec.rationale}</p>
</div>""",
        unsafe_allow_html=True,
    )


def main():
    api_key, lang, provider, selected_model = render_sidebar()
    t = get_texts(lang)

    # 헤더
    st.title(t["title"])
    st.markdown(f"*{t['subtitle']}*")

    # 탭 (v8: 탭1 실험 설계 추가)
    tab_design, tab_input, tab_result = st.tabs(
        [
            "🧪 " + ("실험 설계" if lang == "ko" else "Experiment Design"),
            t["tab_input"],
            t["tab_result"],
        ]
    )

    with tab_design:
        render_design_tab(api_key, lang, provider, model=selected_model)

    with tab_input:
        limiter = SessionLimiter()

        # 탭1에서 만든 설계가 있으면 자동 적용, 없으면 .json 업로드
        design_context = st.session_state.get("design_context")
        if design_context is not None:
            msg = "✅ 탭1에서 만든 설계 적용 중" if lang == "ko" else "✅ Using design from tab 1"
            st.info(f"{msg}: {design_context.sharpened_hypothesis[:40]}…")
        else:
            design_context = render_context_uploader(lang)
        ab_input = render_input_form(t, limiter)

        if ab_input is not None:
            # provider를 ab_input에 설정
            ab_input.provider = provider

            # API 키 확인
            if not api_key:
                st.error(t["api_key_missing"])
                return

            # 요청 제한 확인
            if not limiter.check_and_increment():
                st.error(t["request_limit_warning"])
                return

            # 분석 실행
            with st.spinner(t["analyzing"]):
                try:
                    # Step 1: 통계 분석 (API 없음)
                    with st.status(t["step_stats"]):
                        stats = analyze_stats(ab_input)

                    # Context Loop: 설계 약속 대비 대조 (deterministic, API 없음)
                    if design_context is not None:
                        observed = build_observed_result(ab_input, stats)
                        st.session_state.context_violations = context_loop_guard(
                            design_context, observed
                        )
                    else:
                        st.session_state.context_violations = []

                    # Step 2: 편향 감지
                    with st.status(t["step_bias"]):
                        bias_report = detect_bias(ab_input, stats, api_key, lang, provider, model=selected_model)

                    # Step 3: 추천 생성
                    with st.status(t["step_recommend"]):
                        recommendation = recommend(ab_input, stats, bias_report, api_key, lang, provider, model=selected_model)

                    # BriefOutput 조립
                    brief = BriefOutput(
                        statistical=stats,
                        bias_report=bias_report,
                        recommendation=recommendation,
                        lang=lang,
                    )

                    # 세션에 결과 저장
                    st.session_state.brief_output = brief
                    st.session_state.ab_input = ab_input

                    st.success("✅ 분석 완료!" if lang == "ko" else "✅ Analysis complete!")
                    st.info(
                        "결과 탭을 클릭하여 분석 결과를 확인하세요."
                        if lang == "ko"
                        else "Click the Result tab to view analysis."
                    )

                except Exception as e:
                    st.error(f"분석 중 오류가 발생했습니다: {e}")

    with tab_result:
        if "brief_output" not in st.session_state:
            st.info(t["no_result_yet"])
        else:
            brief = st.session_state.brief_output
            t_result = get_texts(brief.lang)

            render_context_loop(st.session_state.get("context_violations", []), brief.lang)
            render_stats(brief.statistical, t_result)
            st.divider()
            render_bias(brief.bias_report, t_result)
            st.divider()
            if brief.causal_alt:
                render_causal(brief.causal_alt, t_result)
                st.divider()
            render_recommendation(brief.recommendation, t_result)


if __name__ == "__main__":
    main()
