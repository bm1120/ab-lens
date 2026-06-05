"""LLM 클라이언트 추상화 모듈

Anthropic 직접 연결과 OpenRouter 연결을 통합하여 제공합니다.
"""

import anthropic
from openai import OpenAI
from openai import AuthenticationError as OAIAuthError
from openai import RateLimitError as OAIRateLimitError
from openai import APIError as OAIAPIError

from src.schemas import LLMProvider

# 모델 ID는 2026-06-03 실제 검증 기준.
#  - Claude Code(OAuth)/Anthropic: 하이픈 표기 (claude-sonnet-4-5)
#  - OpenRouter: 점 표기 (anthropic/claude-sonnet-4.5)
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"     # 구형 3.5(EOL)에서 교체
CLAUDE_CODE_MODEL = "claude-haiku-4-5-20251001"   # OAuth 200 검증, 기본(빠름/한도 여유)
OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"  # OpenRouter 카탈로그 검증

# ── provider별 선택 가능 모델 목록 ────────────────────────────────────────────
# Claude Code 구독(OAuth): 하이픈 표기. haiku만 200, 상위는 구독 한도에 따라 429 가능(ID는 유효).
CLAUDE_CODE_MODELS: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-opus-4-8",
]
# Anthropic 직접 API 키: 하이픈 표기, 최신 4.x (구형 3.5/3.7 제거)
ANTHROPIC_MODELS: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
]
# OpenRouter: 점 표기 (카탈로그 /models 검증)
OPENROUTER_MODELS: list[str] = [
    # Anthropic
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-opus-4.8",
    # OpenAI — 최신
    "openai/gpt-5.5",
    "openai/gpt-5.4",
    "openai/gpt-5",
    "openai/gpt-5-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o3",
    "openai/o4-mini",
    # Google Gemini — 최신
    "google/gemini-3.5-flash",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    # Meta
    "meta-llama/llama-3.3-70b-instruct",
]
# ── 판정(judge) 전용 모델 ──────────────────────────────────────────────────
# HQS LLM judge는 룰 가이드 Y/P/N 분류 + temperature=0 결정론이라 Haiku로 충분(T1c 검증: 게이트 97%).
# 생성/구체화는 사용자가 고른 모델(추론 집약)을 쓰되, 판정만 항상 저비용·결정론 Haiku로 고정.
_JUDGE_MODEL_BY_PROVIDER: dict[LLMProvider, str] = {
    LLMProvider.CLAUDE_CODE: "claude-haiku-4-5-20251001",
    LLMProvider.ANTHROPIC: "claude-haiku-4-5-20251001",
    LLMProvider.OPENROUTER: "anthropic/claude-haiku-4.5",
}
JUDGE_MODEL_DEFAULT = "claude-haiku-4-5-20251001"


def judge_model_for(provider) -> str:
    """판정 전용 Haiku 모델 ID (provider별 표기 차이 반영). provider 불명 시 기본 Haiku."""
    return _JUDGE_MODEL_BY_PROVIDER.get(provider, JUDGE_MODEL_DEFAULT)


OAUTH_BETA_HEADER = "oauth-2025-04-20"
MAX_TOKENS = 4096  # Anthropic 기본 (진단상 절단 없음)
# OpenRouter 추론 모델(gpt-5 등)은 추론 토큰이 예산을 잠식 → 출력 JSON 절단. 상향으로 방지.
# (provider-prompting-diagnostic.md: GPT sharpen 2/3 절단 → 8192로)
MAX_TOKENS_OPENROUTER = 8192


class TruncatedResponseError(RuntimeError):
    """응답이 max_tokens로 절단됨(finish_reason=length / stop_reason=max_tokens).

    절단된 불완전 JSON을 조용히 반환하지 않고 호출부(call_structured)가 재시도/명확실패하도록 신호.
    """
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
    temperature: float | None = None,
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
        return _call_anthropic(prompt=prompt, system=system, api_key=api_key, model=model or ANTHROPIC_MODEL, temperature=temperature)
    elif provider == LLMProvider.CLAUDE_CODE:
        return _call_claude_code(prompt=prompt, system=system, token=api_key, model=model or CLAUDE_CODE_MODEL, temperature=temperature)
    elif provider == LLMProvider.OPENROUTER:
        return _call_openrouter(prompt=prompt, system=system, api_key=api_key, model=model or OPENROUTER_MODEL, temperature=temperature)
    else:
        raise ValueError(f"지원하지 않는 provider: {provider}")


def _call_claude_code(prompt: str, system: str, token: str, model: str = CLAUDE_CODE_MODEL,
                      temperature: float | None = None) -> str:
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
            **({"temperature": temperature} if temperature is not None else {}),
        )
        block = response.content[0]
        if not isinstance(block, anthropic.types.TextBlock):
            raise RuntimeError(f"예상치 못한 응답 블록 타입: {type(block)}")
        if response.stop_reason == "max_tokens":   # 절단 — 불완전 JSON 조용히 반환 금지
            raise TruncatedResponseError(f"Claude Code 응답 절단(stop_reason=max_tokens, model={model})")
        return block.text
    except anthropic.AuthenticationError as e:
        raise ValueError(f"Claude Code OAuth 인증 오류: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError(f"Claude Code 요청 한도 초과: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude Code API 오류: {e}") from e


def _call_anthropic(prompt: str, system: str, api_key: str, model: str = ANTHROPIC_MODEL,
                    temperature: float | None = None) -> str:
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
            **({"temperature": temperature} if temperature is not None else {}),
        )
        # content[0]가 TextBlock임을 보장
        block = response.content[0]
        if not isinstance(block, anthropic.types.TextBlock):
            raise RuntimeError(f"예상치 못한 응답 블록 타입: {type(block)}")
        if response.stop_reason == "max_tokens":   # 절단 — 불완전 JSON 조용히 반환 금지
            raise TruncatedResponseError(f"Anthropic 응답 절단(stop_reason=max_tokens, model={model})")
        return block.text
    except anthropic.AuthenticationError as e:
        raise ValueError(f"Anthropic 인증 오류: {e}") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError(f"Anthropic 요청 한도 초과: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API 오류: {e}") from e


def _call_openrouter(prompt: str, system: str, api_key: str, model: str = OPENROUTER_MODEL,
                     temperature: float | None = None) -> str:
    """OpenAI SDK로 OpenRouter 호출 (OpenAI 호환 API)"""
    try:
        client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS_OPENROUTER,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            extra_headers={
                "HTTP-Referer": OPENROUTER_HTTP_REFERER,
                "X-Title": OPENROUTER_APP_TITLE,
            },
            **({"temperature": temperature} if temperature is not None else {}),
        )
        choice = response.choices[0]
        content = choice.message.content
        # content=None(추론 모델이 예산을 다 써 빈 출력) / finish_reason=length(절단) 모두
        # 같은 계열 → TruncatedResponseError 로 신호해 call_structured 가 재시도하게 한다.
        if not content:
            raise TruncatedResponseError(
                f"OpenRouter 응답 content 없음(model={model}, finish_reason={choice.finish_reason})")
        if choice.finish_reason == "length":
            raise TruncatedResponseError(
                f"OpenRouter 응답 절단(finish_reason=length, model={model}, max_tokens={MAX_TOKENS_OPENROUTER})")
        return content
    except OAIAuthError as e:
        raise ValueError(f"OpenRouter 인증 오류: {e}") from e
    except OAIRateLimitError as e:
        raise RuntimeError(f"OpenRouter 요청 한도 초과: {e}") from e
    except OAIAPIError as e:
        raise RuntimeError(f"OpenRouter API 오류: {e}") from e
