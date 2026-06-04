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


def call_structured(
    prompt: str,
    system: str,
    schema: type[T],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
    temperature: float | None = None,
) -> T:
    """LLM 호출 → JSON 추출 → schema 로 검증된 모델 반환.

    schema 의 JSON Schema 를 system 프롬프트에 주입해 필드명 불일치를 방지한다.
    temperature: 판정류 호출은 0으로 재현성을 높일 수 있다(기본 None=provider 기본값).
    """
    guided_system = system + _schema_instruction(schema)
    text = call_llm(prompt=prompt, system=guided_system, api_key=api_key, provider=provider,
                    lang=lang, model=model, temperature=temperature)
    return schema.model_validate(extract_json(text))
