"""자격증명 로더.

ab-lens 는 기본적으로 사용자가 UI 에서 키를 입력하지만, 로컬 개발/시연 시
~/.hermes/.env 에 있는 OPENROUTER_API_KEY / CLAUDE_CODE_OAUTH_TOKEN 을 자동
로드해 입력을 생략한다. 우선순위: OS 환경변수 > .env 파일.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

HERMES_ENV = Path.home() / ".hermes" / ".env"


def load_env_file(path: Path = HERMES_ENV) -> dict[str, str]:
    """KEY=VALUE .env 파일을 파싱한다(주석/빈줄 무시, 따옴표 제거)."""
    result: dict[str, str] = {}
    if not Path(path).exists():
        return result
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def get_credential(name: str, env_path: Path = HERMES_ENV) -> Optional[str]:
    """자격증명 조회. OS 환경변수가 .env 파일보다 우선."""
    return os.environ.get(name) or load_env_file(env_path).get(name)
