"""LLM 텍스트 → 구조화 JSON 헬퍼."""
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from src.llm_json import call_structured, extract_json
from src.schemas import LLMProvider


def test_extract_json_from_code_block():
    text = '설명\n```json\n{"a": 1}\n```\n끝'
    assert extract_json(text) == {"a": 1}


def test_extract_json_bare():
    assert extract_json('앞 {"a": 2, "b": [1,2]} 뒤') == {"a": 2, "b": [1, 2]}


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError):
        extract_json("JSON 없음")


class _Model(BaseModel):
    name: str
    count: int


def test_call_structured_parses_and_validates():
    with patch("src.llm_json.call_llm", return_value='```json\n{"name": "x", "count": 3}\n```'):
        out = call_structured(
            prompt="p", system="s", schema=_Model,
            api_key="k", provider=LLMProvider.ANTHROPIC,
        )
    assert isinstance(out, _Model)
    assert out.name == "x" and out.count == 3


def test_call_structured_propagates_validation_error():
    with patch("src.llm_json.call_llm", return_value='{"name": "x"}'):  # count 누락
        with pytest.raises(Exception):
            call_structured(
                prompt="p", system="s", schema=_Model,
                api_key="k", provider=LLMProvider.ANTHROPIC,
            )
