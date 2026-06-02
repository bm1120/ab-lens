"""Claude Code OAuth 경로 (auth_token + oauth 베타 헤더, 구독 모델)."""
from unittest.mock import MagicMock, patch

from src.llm_client import CLAUDE_CODE_MODEL, OAUTH_BETA_HEADER, call_llm
from src.schemas import LLMProvider


def _fake_client_returning(text):
    client = MagicMock()
    block = MagicMock()
    block.text = text
    # isinstance(block, TextBlock) 통과시키기 위해 실제 TextBlock 으로
    import anthropic
    real_block = anthropic.types.TextBlock(type="text", text=text, citations=None)
    resp = MagicMock()
    resp.content = [real_block]
    client.messages.create.return_value = resp
    return client


def test_claude_code_uses_oauth_auth_token_and_beta_header():
    fake = _fake_client_returning("hello")
    with patch("src.llm_client.anthropic.Anthropic", return_value=fake) as ctor:
        out = call_llm(prompt="p", system="s", api_key="sk-ant-oat01-x",
                       provider=LLMProvider.CLAUDE_CODE)
    assert out == "hello"
    # auth_token(=Bearer) 으로 생성, x-api-key 아님
    assert ctor.call_args.kwargs.get("auth_token") == "sk-ant-oat01-x"
    assert ctor.call_args.kwargs["default_headers"]["anthropic-beta"] == OAUTH_BETA_HEADER
    # 구독 모델 사용
    assert fake.messages.create.call_args.kwargs["model"] == CLAUDE_CODE_MODEL
