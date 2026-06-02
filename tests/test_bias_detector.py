"""
편향 감지 에이전트 테스트
- anthropic API 호출을 mock으로 처리
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.schemas import ABTestInput, StatisticalResult


SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def load_scenario(name: str) -> ABTestInput:
    with open(SCENARIOS_DIR / f"{name}.json", encoding="utf-8") as f:
        data = json.load(f)
    return ABTestInput(**data)


def make_mock_stats() -> StatisticalResult:
    return StatisticalResult(
        effect_size_pp=5.0,
        effect_size_relative_pct=50.0,
        is_significant=True,
        power_pct=95.0,
        srm_detected=False,
        srm_detail=None,
        additional_sample_needed=None,
        interpretation="effect_size_pp=+5.00pp, p_value=0.0200, power=95.0%, srm=no",
    )


MOCK_BIAS_RESPONSE = {
    "biases": [
        {
            "name": "Confirmation Bias",
            "severity": "medium",
            "description": "실험 전 강한 기대값이 있어 확증 편향이 발생할 수 있습니다.",
            "counter": "사전 등록(pre-registration)을 통해 가설을 고정하세요.",
            "paper_reference": "Greenwald, A.G. et al. (1996)",
        }
    ],
    "overall_risk": "medium",
}


class TestDetectBias:
    """detect_bias 함수 테스트 (API mock 사용)"""

    @patch("src.llm_client.anthropic.Anthropic")
    def test_detect_bias_returns_bias_report(self, mock_anthropic_class):
        """정상 응답 시 BiasReport 반환"""
        from src.agents.bias_detector import detect_bias

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_block = MagicMock(spec=["text"])
        mock_block.text = json.dumps(MOCK_BIAS_RESPONSE)
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        ab_input = load_scenario("clear_win")
        stats = make_mock_stats()

        import anthropic as _anthropic
        with patch.object(_anthropic.types, "TextBlock", type(mock_block)):
            result = detect_bias(ab_input, stats, "fake-api-key", "ko")

        assert len(result.biases) == 1
        assert result.biases[0].name == "Confirmation Bias"
        assert result.overall_risk == "medium"

    @patch("src.llm_client.anthropic.Anthropic")
    def test_detect_bias_uses_prompt_caching(self, mock_anthropic_class):
        """Prompt Caching이 적용되는지 확인"""
        from src.agents.bias_detector import detect_bias

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_block = MagicMock(spec=["text"])
        mock_block.text = json.dumps(MOCK_BIAS_RESPONSE)
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        ab_input = load_scenario("clear_win")
        stats = make_mock_stats()

        import anthropic as _anthropic
        with patch.object(_anthropic.types, "TextBlock", type(mock_block)):
            detect_bias(ab_input, stats, "fake-api-key", "ko")

        call_kwargs = mock_client.messages.create.call_args
        system_arg = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")

        assert system_arg is not None
        assert isinstance(system_arg, list)
        assert len(system_arg) > 0
        assert system_arg[0].get("cache_control", {}).get("type") == "ephemeral"

    @patch("src.llm_client.anthropic.Anthropic")
    def test_detect_bias_english(self, mock_anthropic_class):
        """영어 모드에서도 정상 동작"""
        from src.agents.bias_detector import detect_bias

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_block = MagicMock(spec=["text"])
        mock_block.text = json.dumps(MOCK_BIAS_RESPONSE)
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        ab_input = load_scenario("clear_win")
        stats = make_mock_stats()

        import anthropic as _anthropic
        with patch.object(_anthropic.types, "TextBlock", type(mock_block)):
            result = detect_bias(ab_input, stats, "fake-api-key", "en")

        assert result is not None
        assert result.overall_risk in ["low", "medium", "high"]

    @patch("src.llm_client.anthropic.Anthropic")
    def test_detect_bias_handles_json_in_codeblock(self, mock_anthropic_class):
        """마크다운 코드 블록으로 감싸진 JSON도 파싱 가능"""
        from src.agents.bias_detector import detect_bias

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        wrapped_json = f"```json\n{json.dumps(MOCK_BIAS_RESPONSE)}\n```"
        mock_block = MagicMock(spec=["text"])
        mock_block.text = wrapped_json
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        ab_input = load_scenario("clear_win")
        stats = make_mock_stats()

        import anthropic as _anthropic
        with patch.object(_anthropic.types, "TextBlock", type(mock_block)):
            result = detect_bias(ab_input, stats, "fake-api-key", "ko")

        assert result is not None
        assert len(result.biases) == 1
