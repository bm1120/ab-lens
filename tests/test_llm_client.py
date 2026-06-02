"""
LLM 클라이언트 테스트
- 실제 API 호출 없이 mock으로 검증
"""

import pytest
from unittest.mock import patch, MagicMock

from src.schemas import LLMProvider
from src.llm_client import (
    call_llm,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_APP_TITLE,
    ANTHROPIC_MODEL,
    OPENROUTER_MODEL,
)


# ─────────────────────────── 공통 픽스처 ───────────────────────────

FAKE_ANTHROPIC_KEY = "sk-ant-fake-key"
FAKE_OPENROUTER_KEY = "sk-or-fake-key"
SYSTEM_PROMPT = "You are a helpful assistant."
USER_PROMPT = "Hello, world!"
EXPECTED_RESPONSE = "Test response text"


# ─────────────────────────── Anthropic 테스트 ───────────────────────────

class TestAnthropicProvider:
    """Anthropic SDK 경로 테스트"""

    @patch("src.llm_client.anthropic.Anthropic")
    def test_anthropic_provider_calls_anthropic_sdk(self, mock_anthropic_class):
        """Anthropic provider 선택 시 anthropic SDK가 호출되는지 확인"""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_block = MagicMock(spec=["text"])
        mock_block.text = EXPECTED_RESPONSE
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        import anthropic as _anthropic
        with patch.object(_anthropic.types, "TextBlock", type(mock_block)):
            result = call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key=FAKE_ANTHROPIC_KEY,
                provider=LLMProvider.ANTHROPIC,
            )

        # anthropic.Anthropic 클라이언트가 생성되었는지 확인
        mock_anthropic_class.assert_called_once_with(api_key=FAKE_ANTHROPIC_KEY)
        # messages.create가 호출되었는지 확인
        mock_client.messages.create.assert_called_once()
        assert result == EXPECTED_RESPONSE

    @patch("src.llm_client.anthropic.Anthropic")
    def test_anthropic_uses_prompt_caching(self, mock_anthropic_class):
        """Anthropic provider 사용 시 Prompt Caching이 적용되는지 확인"""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_block = MagicMock()
        mock_block.text = EXPECTED_RESPONSE
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        import anthropic as _anthropic

        with patch("src.llm_client.anthropic.types.TextBlock", type(mock_block)):
            call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key=FAKE_ANTHROPIC_KEY,
                provider=LLMProvider.ANTHROPIC,
            )

        call_kwargs = mock_client.messages.create.call_args
        system_arg = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")

        assert system_arg is not None
        assert isinstance(system_arg, list)
        assert len(system_arg) > 0
        cache_control = system_arg[0].get("cache_control", {})
        assert cache_control.get("type") == "ephemeral", (
            "Anthropic provider는 Prompt Caching(ephemeral)을 사용해야 합니다."
        )

    @patch("src.llm_client.anthropic.Anthropic")
    def test_anthropic_auth_error_raises_value_error(self, mock_anthropic_class):
        """Anthropic 인증 오류 → ValueError로 변환"""
        import anthropic as _anthropic

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = _anthropic.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body={"error": {"message": "Invalid API key"}},
        )

        with pytest.raises(ValueError, match="Anthropic 인증 오류"):
            call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key="invalid-key",
                provider=LLMProvider.ANTHROPIC,
            )

    @patch("src.llm_client.anthropic.Anthropic")
    def test_anthropic_rate_limit_raises_runtime_error(self, mock_anthropic_class):
        """Anthropic 요청 한도 초과 → RuntimeError로 변환"""
        import anthropic as _anthropic

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = _anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "Rate limit exceeded"}},
        )

        with pytest.raises(RuntimeError, match="Anthropic 요청 한도 초과"):
            call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key=FAKE_ANTHROPIC_KEY,
                provider=LLMProvider.ANTHROPIC,
            )


# ─────────────────────────── OpenRouter 테스트 ───────────────────────────

class TestOpenRouterProvider:
    """OpenRouter (OpenAI SDK) 경로 테스트"""

    @patch("src.llm_client.OpenAI")
    def test_openrouter_provider_calls_openai_sdk(self, mock_openai_class):
        """OpenRouter provider 선택 시 OpenAI SDK가 호출되는지 확인"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = EXPECTED_RESPONSE
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        result = call_llm(
            prompt=USER_PROMPT,
            system=SYSTEM_PROMPT,
            api_key=FAKE_OPENROUTER_KEY,
            provider=LLMProvider.OPENROUTER,
        )

        # OpenAI 클라이언트가 올바른 base_url로 생성되었는지 확인
        mock_openai_class.assert_called_once_with(
            base_url="https://openrouter.ai/api/v1",
            api_key=FAKE_OPENROUTER_KEY,
        )
        # chat.completions.create가 호출되었는지 확인
        mock_client.chat.completions.create.assert_called_once()
        assert result == EXPECTED_RESPONSE

    @patch("src.llm_client.OpenAI")
    def test_openrouter_includes_required_headers(self, mock_openai_class):
        """OpenRouter 호출 시 HTTP-Referer와 X-Title 헤더가 포함되는지 확인"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = EXPECTED_RESPONSE
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        call_llm(
            prompt=USER_PROMPT,
            system=SYSTEM_PROMPT,
            api_key=FAKE_OPENROUTER_KEY,
            provider=LLMProvider.OPENROUTER,
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        extra_headers = call_kwargs.kwargs.get("extra_headers") or call_kwargs[1].get(
            "extra_headers", {}
        )

        assert extra_headers.get("HTTP-Referer") == OPENROUTER_HTTP_REFERER, (
            f"HTTP-Referer 헤더가 {OPENROUTER_HTTP_REFERER}이어야 합니다."
        )
        assert extra_headers.get("X-Title") == OPENROUTER_APP_TITLE, (
            f"X-Title 헤더가 {OPENROUTER_APP_TITLE}이어야 합니다."
        )

    @patch("src.llm_client.OpenAI")
    def test_openrouter_uses_correct_model(self, mock_openai_class):
        """OpenRouter 호출 시 올바른 모델이 사용되는지 확인"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = EXPECTED_RESPONSE
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        call_llm(
            prompt=USER_PROMPT,
            system=SYSTEM_PROMPT,
            api_key=FAKE_OPENROUTER_KEY,
            provider=LLMProvider.OPENROUTER,
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        model_used = call_kwargs.kwargs.get("model") or call_kwargs[1].get("model")
        assert model_used == OPENROUTER_MODEL

    @patch("src.llm_client.OpenAI")
    def test_openrouter_system_message_in_chat_format(self, mock_openai_class):
        """OpenRouter는 system을 messages 배열의 첫 번째로 전달하는지 확인"""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = EXPECTED_RESPONSE
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        call_llm(
            prompt=USER_PROMPT,
            system=SYSTEM_PROMPT,
            api_key=FAKE_OPENROUTER_KEY,
            provider=LLMProvider.OPENROUTER,
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages", [])

        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == USER_PROMPT


# ─────────────────────────── 공통 에러 처리 테스트 ───────────────────────────

class TestErrorHandling:
    """공통 에러 처리 테스트"""

    @patch("src.llm_client.OpenAI")
    def test_fallback_on_rate_limit(self, mock_openai_class):
        """OpenRouter 요청 한도 초과 → RuntimeError로 변환"""
        from openai import RateLimitError as OAIRateLimitError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_client.chat.completions.create.side_effect = OAIRateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )

        with pytest.raises(RuntimeError, match="OpenRouter 요청 한도 초과"):
            call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key=FAKE_OPENROUTER_KEY,
                provider=LLMProvider.OPENROUTER,
            )

    @patch("src.llm_client.OpenAI")
    def test_openrouter_auth_error_raises_value_error(self, mock_openai_class):
        """OpenRouter 인증 오류 → ValueError로 변환"""
        from openai import AuthenticationError as OAIAuthError

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_client.chat.completions.create.side_effect = OAIAuthError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )

        with pytest.raises(ValueError, match="OpenRouter 인증 오류"):
            call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key="invalid-key",
                provider=LLMProvider.OPENROUTER,
            )

    def test_unsupported_provider_raises_value_error(self):
        """지원하지 않는 provider 값 → ValueError"""
        with pytest.raises((ValueError, AttributeError)):
            call_llm(
                prompt=USER_PROMPT,
                system=SYSTEM_PROMPT,
                api_key="fake-key",
                provider="invalid_provider",  # type: ignore
            )
