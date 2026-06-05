"""편향 감지 에이전트"""

import json
import re

from src.schemas import ABTestInput, StatisticalResult, BiasReport, LLMProvider
from src.prompts.bias_check import SYSTEM_PROMPT_KO, SYSTEM_PROMPT_EN
from src.llm_client import call_llm


def detect_bias(
    input: ABTestInput,
    stats: StatisticalResult,
    api_key: str,
    lang: str = "ko",
    provider: LLMProvider = LLMProvider.ANTHROPIC,
    model: str | None = None,
) -> BiasReport:
    """
    LLM을 사용하여 A/B 테스트의 의사결정 편향을 감지합니다.
    Anthropic 직접 연결 시 Prompt Caching을 적용하여 비용을 절감합니다.
    """
    system_prompt = SYSTEM_PROMPT_KO if lang == "ko" else SYSTEM_PROMPT_EN
    user_message = _build_user_message(input, stats, lang)

    response_text = call_llm(
        prompt=user_message,
        system=system_prompt,
        api_key=api_key,
        provider=provider,
        lang=lang,
        model=model,
    )

    json_data = _extract_json(response_text)
    return BiasReport.model_validate(json_data)


def _build_user_message(input: ABTestInput, stats: StatisticalResult, lang: str) -> str:
    """편향 감지를 위한 사용자 메시지를 구성합니다."""
    if lang == "ko":
        return f"""다음 A/B 테스트 결과를 분석하여 의사결정 편향을 감지해주세요:

## 실험 데이터
- 메트릭: {input.metric_name}
- Treatment 값: {input.treatment_value:.4f} ({input.treatment_value*100:.2f}%)
- Control 값: {input.control_value:.4f} ({input.control_value*100:.2f}%)
- P-Value: {input.p_value:.4f}
- Treatment 샘플 수: {input.sample_size_treatment:,}
- Control 샘플 수: {input.sample_size_control:,}
- 실험 기간: {input.experiment_days}일
- 무작위 배정: {'예' if input.is_random_assignment else '아니오'}
- 다중 메트릭: {'예' if input.multiple_metrics else '아니오'}
- 개발 비용: {f'{input.dev_cost_weeks}주' if input.dev_cost_weeks else '미입력'}
- 비즈니스 우선순위: {input.business_priority or '미입력'}
- 사전 기대값: {input.prior_expectation or '미입력'}
- 비즈니스 맥락: {input.business_context or '미입력'}

## 통계 분석 결과
- 효과 크기: {stats.effect_size_pp:+.2f}pp ({stats.effect_size_relative_pct:+.1f}% 상대 변화)
- 효과 크기 95% 신뢰구간: [{stats.ci_low_pp:+.2f}, {stats.ci_high_pp:+.2f}]pp {'(0 포함)' if stats.ci_includes_zero else '(0 미포함)'}
- (보조) 통계적 유의성: {'유의 (p<0.05)' if stats.is_significant else '비유의 (p≥0.05)'}
- 검정력: {stats.power_pct:.1f}%
- SRM 감지: {'예' if stats.srm_detected else '아니오'}
{f'- SRM 상세: {stats.srm_detail}' if stats.srm_detail else ''}"""
    else:
        return f"""Please analyze the following A/B test results and detect decision-making biases:

## Experiment Data
- Metric: {input.metric_name}
- Treatment Value: {input.treatment_value:.4f} ({input.treatment_value*100:.2f}%)
- Control Value: {input.control_value:.4f} ({input.control_value*100:.2f}%)
- P-Value: {input.p_value:.4f}
- Treatment Sample Size: {input.sample_size_treatment:,}
- Control Sample Size: {input.sample_size_control:,}
- Experiment Duration: {input.experiment_days} days
- Random Assignment: {'Yes' if input.is_random_assignment else 'No'}
- Multiple Metrics: {'Yes' if input.multiple_metrics else 'No'}
- Dev Cost: {f'{input.dev_cost_weeks} weeks' if input.dev_cost_weeks else 'Not provided'}
- Business Priority: {input.business_priority or 'Not provided'}
- Prior Expectation: {input.prior_expectation or 'Not provided'}
- Business Context: {input.business_context or 'Not provided'}

## Statistical Analysis Results
- Effect Size: {stats.effect_size_pp:+.2f}pp ({stats.effect_size_relative_pct:+.1f}% relative change)
- Effect Size 95% CI: [{stats.ci_low_pp:+.2f}, {stats.ci_high_pp:+.2f}]pp {'(includes 0)' if stats.ci_includes_zero else '(excludes 0)'}
- (secondary) Statistical Significance: {'Significant (p<0.05)' if stats.is_significant else 'Not significant (p≥0.05)'}
- Statistical Power: {stats.power_pct:.1f}%
- SRM Detected: {'Yes' if stats.srm_detected else 'No'}
{f'- SRM Detail: {stats.srm_detail}' if stats.srm_detail else ''}"""


def _extract_json(text: str) -> dict:
    """텍스트에서 JSON을 추출합니다."""
    # 코드 블록에서 JSON 추출
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        return json.loads(code_block_match.group(1))

    # 직접 JSON 파싱 시도
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError(f"JSON을 응답에서 찾을 수 없습니다: {text[:200]}")
