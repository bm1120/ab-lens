"""프로바이더 어댑터 — 절단 감지 + call_structured 재시도 (provider-prompting-diagnostic 반영)."""
import json

import pytest
from pydantic import BaseModel

import src.llm_json as lj
from src.llm_client import MAX_TOKENS, MAX_TOKENS_OPENROUTER, TruncatedResponseError
from src.llm_json import JSONExtractionError, call_structured
from src.schemas import LLMProvider


class Tiny(BaseModel):
    a: str
    b: int


_GOOD = '{"a": "x", "b": 1}'


def _patch_call(monkeypatch, side_effect):
    calls = {"n": 0}

    def fake(**kw):
        calls["n"] += 1
        r = side_effect(calls["n"])
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(lj, "call_llm", fake)
    return calls


# ── 상수/예외 계층 ─────────────────────────────────────────────────────
def test_openrouter_budget_higher():
    assert MAX_TOKENS_OPENROUTER > MAX_TOKENS   # 추론 모델 절단 방지

def test_truncated_is_runtimeerror():
    assert issubclass(TruncatedResponseError, RuntimeError)


# ── 재시도: 절단 → 성공 ────────────────────────────────────────────────
def test_retry_on_truncation_then_success(monkeypatch):
    calls = _patch_call(monkeypatch, lambda n: TruncatedResponseError("절단") if n == 1 else _GOOD)
    out = call_structured("p", "s", Tiny, api_key="k", provider=LLMProvider.OPENROUTER)
    assert out.a == "x" and out.b == 1
    assert calls["n"] == 2   # 1회 재시도로 회복


def test_retry_on_json_extraction_failure(monkeypatch):
    calls = _patch_call(monkeypatch, lambda n: "잘린 텍스트 { 없음" if n == 1 else _GOOD)
    out = call_structured("p", "s", Tiny, api_key="k", provider=LLMProvider.OPENROUTER)
    assert out.b == 1 and calls["n"] == 2


# ── 재시도 소진 → 마지막 예외 전파 ─────────────────────────────────────
def test_exhausts_retries_then_raises(monkeypatch):
    calls = _patch_call(monkeypatch, lambda n: TruncatedResponseError("계속 절단"))
    with pytest.raises(TruncatedResponseError):
        call_structured("p", "s", Tiny, api_key="k", provider=LLMProvider.OPENROUTER, max_retries=1)
    assert calls["n"] == 2   # 최초 + 1회 재시도


# ── 인증 오류 등은 재시도하지 않고 즉시 전파 ───────────────────────────
def test_auth_error_not_retried(monkeypatch):
    calls = _patch_call(monkeypatch, lambda n: ValueError("Anthropic 인증 오류"))
    with pytest.raises(ValueError):
        call_structured("p", "s", Tiny, api_key="k", provider=LLMProvider.ANTHROPIC)
    assert calls["n"] == 1   # 재시도 없음


def test_no_retry_when_disabled(monkeypatch):
    calls = _patch_call(monkeypatch, lambda n: JSONExtractionError("no json"))
    with pytest.raises(JSONExtractionError):
        call_structured("p", "s", Tiny, api_key="k", provider=LLMProvider.OPENROUTER, max_retries=0)
    assert calls["n"] == 1
