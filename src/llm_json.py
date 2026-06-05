"""LLM 텍스트 응답 → 구조화 JSON → Pydantic 모델 헬퍼.

탭1 에이전트(expander/sharpener/bias_screener/trivial_router)가 공유한다.
기존 bias_detector._extract_json 과 동일한 추출 규칙을 일반화한 것.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.llm_client import TruncatedResponseError, call_llm
from src.schemas import LLMProvider

T = TypeVar("T", bound=BaseModel)


class JSONExtractionError(ValueError):
    """응답에서 JSON 객체를 찾지 못함 (인증 등 다른 ValueError와 구분 — 재시도 대상)."""


def extract_json(text: str) -> dict:
    """LLM 응답 텍스트에서 JSON 객체를 추출한다 (코드블록 우선, 없으면 첫 {} 블록)."""
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return json.loads(code_block.group(1))
    bare = re.search(r"\{.*\}", text, re.DOTALL)
    if bare:
        return json.loads(bare.group(0))
    raise JSONExtractionError(f"JSON을 응답에서 찾을 수 없습니다: {text[:200]}")


def _schema_instruction(schema: type[BaseModel]) -> str:
    """LLM 이 정확한 필드명으로 답하도록 JSON Schema 를 프롬프트에 주입."""
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
    return (
        "\n\n# 출력 형식 (엄수)\n"
        "아래 JSON Schema 의 properties 키와 **정확히 일치**하는 JSON 객체로만 답하세요. "
        "required 필드를 모두 포함하고, 스키마에 없는 키를 추가하지 마세요. "
        "설명 문장 없이 JSON 만 출력하세요.\n"
        f"```json\n{schema_json}\n```"
    )


# 절단/파싱 실패는 전이성(특히 추론 모델) → 1회 재시도로 완화. 인증·한도 오류는 즉시 전파.
_RETRYABLE = (JSONExtractionError, json.JSONDecodeError, ValidationError, TruncatedResponseError)


def call_structured(
    prompt: str,
    system: str,
    schema: type[T],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
    temperature: float | None = None,
    max_retries: int = 1,
) -> T:
    """LLM 호출 → JSON 추출 → schema 로 검증된 모델 반환.

    schema 의 JSON Schema 를 system 프롬프트에 주입해 필드명 불일치를 방지한다.
    temperature: 판정류 호출은 0으로 재현성을 높일 수 있다(기본 None=provider 기본값).
    절단(TruncatedResponseError)/JSON·스키마 실패 시 max_retries 만큼 재호출(provider 어댑터).
    """
    guided_system = system + _schema_instruction(schema)
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            text = call_llm(prompt=prompt, system=guided_system, api_key=api_key, provider=provider,
                            lang=lang, model=model, temperature=temperature)
            return schema.model_validate(extract_json(text))
        except _RETRYABLE as e:
            last_err = e
            if attempt < max_retries:
                logging.getLogger(__name__).warning(
                    "call_structured 재시도(%d/%d) — %s: %s",
                    attempt + 1, max_retries, type(e).__name__, str(e)[:120])
    raise last_err
