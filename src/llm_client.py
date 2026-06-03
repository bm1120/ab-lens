"""LLM 클라이언트 추상화 모듈

Anthropic 직접 연결과 OpenRouter 연결을 통합하여 제공합니다.
"""

import anthropic
from openai import OpenAI
from openai import AuthenticationError as OAIAuthError
from openai import RateLimitError as OAIRateLimitError
from openai import APIError as OAIAPIError

from src.schemas import LLMProvider

ANTHROPIC_MODEL = "claude-3-5-haiku-20241022"
CLAUDE_CODE_MODEL = "claude-haiku-4-5-20251001"  # Claude Code 구독으로 접근 가능한 모델
OPENROUTER_MODEL = "anthropic/claude-sonnet-4-5"

# ── provider별 선택 가능 모델 목록 ────────────────────────────────────────────
CLAUDE_CODE_MODELS: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20251001",
    "claude-opus-4-5-20251001",
]
ANTHROPIC_MODELS: list[str] = [
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-7-sonnet-20250219",
]
OPENROUTER_MODELS: list[str] = [
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-opus-4-5",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
]
OAUTH_BETA_HEADER = "oauth-2025-04-20"
MAX_TOKENS = 4096  # HypothesisOutput 등 큰 구조화 출력이 잘리지 않도록
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_HTTP_REFERER = "https://github.com/bm1120/ab-lens"
OPENROUTER_APP_TITLE = "ab-lens"


def call_llm(
    prompt: str,
    system: str,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> str:
    """
    LLM을 호출하고 텍스트 응답을 반환합니다.

    Args:
        prompt: 사용자 메시지 (user message)
        system: 시스템 프롬프트
        api_key: API 키
        provider: LLM 제공자 (ANTHROPIC 또는 OPENROUTER)
        lang: 언어 코드 (ko/en, 현재 미사용 — 향후 확장용)
        model: 사용할 모델명. None이면 provider별 기본값 사용.

    Returns:
        LLM 응답 텍스트

    Raises:
        ValueError: 인증 오류
        RuntimeError: 요청 한도 초과 또는 API 오류
    """
    if provider == LLMProvider.ANTHROPIC:
        return _call_anthropic(prompt=prompt, system=system, api_key=api_key, model=model or ANTHROPIC_MODEL)
    elif provider == LLMProvider.CLAUDE_CODE:
        return _call_claude_code(prompt=prompt, system=system, token=api_key, model=model or CLAUDE_CODE_MODEL)
    elif provider == LLMProvider.OPENROUTER:
        return _call_openrouter(prompt=prompt, system=system, api_key=api_key, model=model or OPENROUTER_MODEL)
    else:
        raise ValueError(f"지원하지 않는 provider: {provider}")


def _call_claude_code(prompt: str, system: str, token: str, model: str = CLAUDE_CODE_MODEL) -> str:
    """Claude Code 구독 OAuth 토큰으로 호출 (auth_token=Bearer + oauth 베타 헤더)."""
    try:
        client = anthropic.Anthropic(
            auth_token=token,
            default_headers={"anthropic-beta": OAUTH_BETA_HEADER},
        )
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        if not isinstance(block, anthropic.types.TextBlock):
            raise RuntimeError(f"예상치 못한 응답 블록 타입: {type(block)}")
        return block.text
    except anthropic.AuthenticationError as e:
        raise ValueError(f"Claude Code OAuth 인증 오류: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError(f"Claude Code 요청 한도 초과: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude Code API 오류: {e}") from e


def _call_anthropic(prompt: str, system: str, api_key: str, model: str = ANTHROPIC_MODEL) -> str:
    """Anthropic SDK로 LLM 호출 (Prompt Caching 적용)"""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},  # Prompt Caching
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        # content[0]가 TextBlock임을 보장
        block = response.content[0]
        if not isinstance(block, anthropic.types.TextBlock):
            raise RuntimeError(f"예상치 못한 응답 블록 타입: {type(block)}")
        return block.text
    except anthropic.AuthenticationError as e:
        raise ValueError(f"Anthropic 인증 오류: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError(f"Anthropic 요청 한도 초과: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API 오류: {e}") from e


def _call_openrouter(prompt: str, system: str, api_key: str, model: str = OPENROUTER_MODEL) -> str:
    """OpenAI SDK로 OpenRouter 호출 (OpenAI 호환 API)"""
    try:
        client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            extra_headers={
                "HTTP-Referer": OPENROUTER_HTTP_REFERER,
                "X-Title": OPENROUTER_APP_TITLE,
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("OpenRouter 응답에 content가 없습니다.")
        return content
    except OAIAuthError as e:
        raise ValueError(f"OpenRouter 인증 오류: {e}") from e
    except OAIRateLimitError as e:
        raise RuntimeError(f"OpenRouter 요청 한도 초과: {e}") from e
    except OAIAPIError as e:
        raise RuntimeError(f"OpenRouter API 오류: {e}") from e
