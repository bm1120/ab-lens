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


def render_sidebar() -> tuple[str, str, LLMProvider]:
    """사이드바 렌더링. (api_key, lang, provider) 반환"""
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

        # Provider 선택
        provider_options = {
            t["provider_anthropic"]: LLMProvider.ANTHROPIC,
            t["provider_openrouter"]: LLMProvider.OPENROUTER,
        }
        provider_label = st.radio(
            t["provider_select"],
            options=list(provider_options.keys()),
            index=0,
        )
        provider = provider_options[provider_label]

        # provider에 따라 API 키 레이블 변경
        if provider == LLMProvider.ANTHROPIC:
            api_key_label = t["api_key_label_anthropic"]
            api_key_placeholder = "sk-ant-..."
        else:
            api_key_label = t["api_key_label_openrouter"]
            api_key_placeholder = "sk-or-..."

        api_key = st.text_input(
            api_key_label,
            type="password",
            help=t["sidebar_api_key_help"],
            placeholder=api_key_placeholder,
        )

        st.divider()

        # 요청 카운터 표시
        limiter = SessionLimiter()
        remaining = limiter.remaining_requests
        st.metric(t["remaining_requests"], f"{remaining}/10")

        if remaining < 3:
            st.warning(t["request_limit_warning"])

    return api_key, st.session_state.lang, provider


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
    api_key, lang, provider = render_sidebar()
    t = get_texts(lang)

    # 헤더
    st.title(t["title"])
    st.markdown(f"*{t['subtitle']}*")

    # 탭
    tab_input, tab_result = st.tabs([t["tab_input"], t["tab_result"]])

    with tab_input:
        limiter = SessionLimiter()

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

                    # Step 2: 편향 감지
                    with st.status(t["step_bias"]):
                        bias_report = detect_bias(ab_input, stats, api_key, lang, provider)

                    # Step 3: 추천 생성
                    with st.status(t["step_recommend"]):
                        recommendation = recommend(ab_input, stats, bias_report, api_key, lang, provider)

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
