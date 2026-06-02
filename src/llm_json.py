"""LLM 텍스트 응답 → 구조화 JSON → Pydantic 모델 헬퍼.

탭1 에이전트(expander/sharpener/bias_screener/trivial_router)가 공유한다.
기존 bias_detector._extract_json 과 동일한 추출 규칙을 일반화한 것.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from src.llm_client import call_llm
from src.schemas import LLMProvider

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> dict:
    """LLM 응답 텍스트에서 JSON 객체를 추출한다 (코드블록 우선, 없으면 첫 {} 블록)."""
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return json.loads(code_block.group(1))
    bare = re.search(r"\{.*\}", text, re.DOTALL)
    if bare:
        return json.loads(bare.group(0))
    raise ValueError(f"JSON을 응답에서 찾을 수 없습니다: {text[:200]}")


def call_structured(
    prompt: str,
    system: str,
    schema: type[T],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
) -> T:
    """LLM 호출 → JSON 추출 → schema 로 검증된 모델 반환."""
    text = call_llm(prompt=prompt, system=system, api_key=api_key, provider=provider, lang=lang)
    return schema.model_validate(extract_json(text))
