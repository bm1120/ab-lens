"""추천 에이전트"""

import json
import re

from src.schemas import ABTestInput, StatisticalResult, BiasReport, Recommendation, LLMProvider
from src.prompts.recommender import SYSTEM_PROMPT_KO, SYSTEM_PROMPT_EN
from src.llm_client import call_llm


def recommend(
    input: ABTestInput,
    stats: StatisticalResult,
    bias: BiasReport,
    api_key: str,
    lang: str = "ko",
    provider: LLMProvider = LLMProvider.ANTHROPIC,
    model: str | None = None,
) -> Recommendation:
    """
    LLM을 사용하여 A/B 테스트 결과에 대한 비즈니스 추천을 생성합니다.
    Anthropic 직접 연결 시 Prompt Caching을 적용하여 비용을 절감합니다.
    """
    system_prompt = SYSTEM_PROMPT_KO if lang == "ko" else SYSTEM_PROMPT_EN
    user_message = _build_user_message(input, stats, bias, lang)

    response_text = call_llm(
        prompt=user_message,
        system=system_prompt,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )

    json_data = _extract_json(response_text)
    return Recommendation.model_validate(json_data)


def _build_user_message(
    input: ABTestInput, stats: StatisticalResult, bias: BiasReport, lang: str
) -> str:
    """추천 생성을 위한 사용자 메시지를 구성합니다."""
    # 편향 요약
    biases_summary = "\n".join(
        [f"  - {b.name} (심각도: {b.severity})" for b in bias.biases]
        if lang == "ko"
        else [f"  - {b.name} (severity: {b.severity})" for b in bias.biases]
    )

    if lang == "ko":
        return f"""다음 A/B 테스트 분석 결과를 바탕으로 비즈니스 추천을 제공해주세요:

## 실험 기본 정보
- 메트릭: {input.metric_name}
- 비즈니스 우선순위: {input.business_priority or '미입력'}
- 개발 비용: {f'{input.dev_cost_weeks}주' if input.dev_cost_weeks else '미입력'}
- 실험 기간: {input.experiment_days}일
- 무작위 배정: {'예' if input.is_random_assignment else '아니오'}
- 다중 메트릭: {'예' if input.multiple_metrics else '아니오'}
- 비즈니스 맥락: {input.business_context or '없음'}

## 통계 분석 결과 (효과크기 중심)
- 효과 크기: {stats.effect_size_pp:+.2f}pp ({stats.effect_size_relative_pct:+.1f}% 상대 변화)
- 효과 크기 95% 신뢰구간: [{stats.ci_low_pp:+.2f}, {stats.ci_high_pp:+.2f}]pp {'— 0 포함(효과 방향 불확실)' if stats.ci_includes_zero else '— 0 미포함(방향 일관)'}
- 검정력: {stats.power_pct:.1f}%
- (보조) 통계적 유의성: {'유의 (p<0.05)' if stats.is_significant else '비유의 (p≥0.05)'}, p={input.p_value:.4f} — ※p값은 보조 지표일 뿐, 효과크기·신뢰구간·실질적 유의성을 우선 판단
- SRM: {'감지됨 ⚠️' if stats.srm_detected else '정상'}
{f'- SRM 상세: {stats.srm_detail}' if stats.srm_detail else ''}
{f'- 추가 필요 샘플: {stats.additional_sample_needed:,}' if stats.additional_sample_needed else ''}

## 편향 분석 결과
- 전체 위험도: {bias.overall_risk}
- 감지된 편향:
{biases_summary or '  없음'}"""
    else:
        return f"""Please provide a business recommendation based on the following A/B test analysis:

## Experiment Basic Information
- Metric: {input.metric_name}
- Business Priority: {input.business_priority or 'Not provided'}
- Dev Cost: {f'{input.dev_cost_weeks} weeks' if input.dev_cost_weeks else 'Not provided'}
- Experiment Duration: {input.experiment_days} days
- Random Assignment: {'Yes' if input.is_random_assignment else 'No'}
- Multiple Metrics: {'Yes' if input.multiple_metrics else 'No'}
- Business Context: {input.business_context or 'None'}

## Statistical Analysis Results (effect-size-centered)
- Effect Size: {stats.effect_size_pp:+.2f}pp ({stats.effect_size_relative_pct:+.1f}% relative change)
- Effect Size 95% CI: [{stats.ci_low_pp:+.2f}, {stats.ci_high_pp:+.2f}]pp {'— includes 0 (direction uncertain)' if stats.ci_includes_zero else '— excludes 0 (consistent direction)'}
- Statistical Power: {stats.power_pct:.1f}%
- (secondary) Statistical Significance: {'Significant (p<0.05)' if stats.is_significant else 'Not significant (p≥0.05)'}, p={input.p_value:.4f} — Note: p-value is secondary; prioritize effect size, CI, and practical significance
- SRM: {'Detected ⚠️' if stats.srm_detected else 'OK'}
{f'- SRM Detail: {stats.srm_detail}' if stats.srm_detail else ''}
{f'- Additional Sample Needed: {stats.additional_sample_needed:,}' if stats.additional_sample_needed else ''}

## Bias Analysis Results
- Overall Risk: {bias.overall_risk}
- Detected Biases:
{biases_summary or '  None'}"""


def _extract_json(text: str) -> dict:
    """텍스트에서 JSON을 추출합니다."""
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        return json.loads(code_block_match.group(1))

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError(f"JSON을 응답에서 찾을 수 없습니다: {text[:200]}")
