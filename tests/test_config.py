"""자격증명 로더 — ~/.hermes/.env(또는 지정 경로)에서 키를 읽어 UI 입력을 생략."""
import os

from src.config import get_credential, load_env_file


def _write_env(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# 주석\n"
        'OPENROUTER_API_KEY="sk-or-abc"\n'
        "CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-xyz\n"
        "\n"
        "EMPTY=\n"
    )
    return p


def test_load_env_file_parses_keys(tmp_path):
    env = load_env_file(_write_env(tmp_path))
    assert env["OPENROUTER_API_KEY"] == "sk-or-abc"   # 따옴표 제거
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-xyz"


def test_load_env_file_skips_comments_and_blanks(tmp_path):
    env = load_env_file(_write_env(tmp_path))
    assert "# 주석" not in env
    assert env.get("EMPTY") == ""


def test_load_env_file_missing_returns_empty(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == {}


def test_get_credential_from_file(tmp_path):
    assert get_credential("OPENROUTER_API_KEY", env_path=_write_env(tmp_path)) == "sk-or-abc"


def test_get_credential_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-os-env")
    assert get_credential("OPENROUTER_API_KEY", env_path=_write_env(tmp_path)) == "from-os-env"


def test_get_credential_absent_returns_none(tmp_path):
    assert get_credential("NOPE", env_path=_write_env(tmp_path)) is None
