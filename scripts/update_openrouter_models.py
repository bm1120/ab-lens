#!/usr/bin/env python3
"""OpenRouter 카탈로그 기준 ab-lens 모델 목록 자동 업데이트.

실행: uv run python scripts/update_openrouter_models.py
크론: 매주 월요일 09:00 (hermes cron)

업데이트 대상:
  - src/llm_client.py : OPENROUTER_MODEL 기본값, OPENROUTER_MODELS 목록
  - src/hypothesis/multi_model_debate.py : GPT/Gemini debate 슬롯

변경 있으면 git commit + push.
변경 없으면 아무것도 안 함 (cron [SILENT] 패턴).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── 1. OpenRouter 카탈로그 호출 ────────────────────────────────────────────────

def fetch_models(api_key: str) -> list[str]:
    import urllib.request
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [m["id"] for m in data.get("data", [])]


# ── 2. 최신 모델 선택 로직 ────────────────────────────────────────────────────

def _version_key(model_id: str) -> tuple:
    """모델 ID에서 버전 숫자 추출 → 정렬키. 예: 'claude-sonnet-4.6' → (4, 6)"""
    nums = re.findall(r"\d+", model_id.split("/")[-1])
    return tuple(int(n) for n in nums)


def pick_latest(models: list[str], prefix: str, exclude: list[str] | None = None) -> str | None:
    """prefix로 시작하는 모델 중 버전 최신 1개 반환. alias(~) 제외."""
    exclude = exclude or []
    candidates = [
        m for m in models
        if m.startswith(prefix) and not m.startswith("~") and m not in exclude
    ]
    if not candidates:
        return None
    return max(candidates, key=_version_key)


def select_models(all_models: list[str]) -> dict:
    """카탈로그에서 관심 모델 최신 버전 선택."""
    return {
        # Anthropic (OpenRouter 점 표기)
        "sonnet_latest":    pick_latest(all_models, "anthropic/claude-sonnet-4"),
        "sonnet_prev":      pick_latest(all_models, "anthropic/claude-sonnet-4",
                                        exclude=[s for s in [pick_latest(all_models, "anthropic/claude-sonnet-4")] if s]),
        "haiku_latest":     pick_latest(all_models, "anthropic/claude-haiku-4"),
        "opus_latest":      pick_latest(all_models, "anthropic/claude-opus-4",
                                        exclude=[m for m in all_models if "fast" in m]),
        "opus_fast":        pick_latest(all_models, "anthropic/claude-opus-4",
                                        exclude=[m for m in all_models if "fast" not in m]),
        # OpenAI
        "gpt_latest":       pick_latest(all_models, "openai/gpt-5"),
        # Google
        "gemini_latest":    pick_latest(all_models, "google/gemini-3"),
    }


# ── 3. llm_client.py 패치 ────────────────────────────────────────────────────

def build_openrouter_models_block(sel: dict) -> str:
    """OPENROUTER_MODELS 리스트 블록 생성."""
    from datetime import date
    today = date.today().isoformat()

    claude_models = []
    if sel["sonnet_latest"]:
        claude_models.append(f'    "{sel["sonnet_latest"]}",')
    if sel["sonnet_prev"] and sel["sonnet_prev"] != sel["sonnet_latest"]:
        claude_models.append(f'    "{sel["sonnet_prev"]}",')
    if sel["haiku_latest"]:
        claude_models.append(f'    "{sel["haiku_latest"]}",')
    if sel["opus_latest"]:
        claude_models.append(f'    "{sel["opus_latest"]}",')
    if sel["opus_fast"] and sel["opus_fast"] != sel["opus_latest"]:
        claude_models.append(f'    "{sel["opus_fast"]}",')

    lines = [
        f'# OpenRouter: 점 표기 (카탈로그 /models 검증 — {today})',
        'OPENROUTER_MODELS: list[str] = [',
        f'    # Anthropic — 카탈로그 최신 기준',
    ] + claude_models + [
        '    # OpenAI — 최신',
        '    "openai/gpt-5.5",',
        '    "openai/gpt-5.4",',
        '    "openai/gpt-5",',
        '    "openai/gpt-5-mini",',
        '    "openai/gpt-4.1",',
        '    "openai/gpt-4.1-mini",',
        '    "openai/gpt-4o",',
        '    "openai/gpt-4o-mini",',
        '    "openai/o3",',
        '    "openai/o4-mini",',
        '    # Google Gemini — 최신',
        '    "google/gemini-3.5-flash",',
        '    "google/gemini-3.1-pro-preview",',
        '    "google/gemini-3.1-flash-lite",',
        '    "google/gemini-2.5-pro",',
        '    "google/gemini-2.5-flash",',
        '    "google/gemini-2.5-flash-lite",',
        '    # Meta',
        '    "meta-llama/llama-3.3-70b-instruct",',
        ']',
    ]
    return "\n".join(lines)


def patch_llm_client(sel: dict) -> tuple[bool, str]:
    """llm_client.py 패치. 변경 있으면 (True, diff), 없으면 (False, '')."""
    path = ROOT / "src" / "llm_client.py"
    original = path.read_text()
    text = original

    from datetime import date
    today = date.today().isoformat()

    # OPENROUTER_MODEL 기본값
    if sel["sonnet_latest"]:
        text = re.sub(
            r'(OPENROUTER_MODEL\s*=\s*")[^"]+(".*)',
            rf'\g<1>{sel["sonnet_latest"]}\2',
            text,
        )
        # 날짜 주석 갱신
        text = re.sub(
            r'(OPENROUTER_MODEL\s*=\s*"[^"]+".*?검증)[^#\n]*',
            rf'\1 ({today})',
            text,
        )

    # OPENROUTER_MODELS 블록 교체
    new_block = build_openrouter_models_block(sel)
    text = re.sub(
        r"# OpenRouter: 점 표기.*?^]",
        new_block,
        text,
        flags=re.DOTALL | re.MULTILINE,
    )

    if text == original:
        return False, ""
    path.write_text(text)
    return True, _diff(original, text, path.name)


# ── 4. multi_model_debate.py 패치 ─────────────────────────────────────────────

def patch_debate(sel: dict) -> tuple[bool, str]:
    """GPT/Gemini debate 슬롯 최신 모델로 업데이트."""
    path = ROOT / "src" / "hypothesis" / "multi_model_debate.py"
    original = path.read_text()
    text = original

    from datetime import date
    today = date.today().isoformat()

    if sel["gpt_latest"]:
        text = re.sub(
            r'(ModelRole\.GPT\s*:\s*")[^"]+(")',
            rf'\g<1>{sel["gpt_latest"]}\2',
            text,
        )
    if sel["gemini_latest"]:
        text = re.sub(
            r'(ModelRole\.GEMINI\s*:\s*")[^"]+(")',
            rf'\g<1>{sel["gemini_latest"]}\2',
            text,
        )
    # 날짜 주석 갱신
    text = re.sub(
        r"(카탈로그 검증 \()\d{4}-\d{2}-\d{2}(\))",
        rf"\g<1>{today}\2",
        text,
    )

    if text == original:
        return False, ""
    path.write_text(text)
    return True, _diff(original, text, path.name)


def _diff(original: str, updated: str, label: str) -> str:
    """간단한 변경 요약 (변경된 줄만)."""
    lines_orig = original.splitlines()
    lines_new = updated.splitlines()
    changed = []
    for i, (a, b) in enumerate(zip(lines_orig, lines_new), 1):
        if a != b:
            changed.append(f"  L{i}: -{a.strip()}")
            changed.append(f"  L{i}: +{b.strip()}")
    return f"{label}:\n" + "\n".join(changed[:20])


# ── 5. git commit + push ──────────────────────────────────────────────────────

def git_commit_push(changed_files: list[Path], message: str) -> bool:
    try:
        subprocess.run(["git", "add"] + [str(f) for f in changed_files],
                       cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message],
                       cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "push"],
                       cwd=ROOT, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"git 오류: {e.stderr.decode()[:200]}", file=sys.stderr)
        return False


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        # .env에서 로드 시도
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not api_key:
        print("[SILENT]")  # 크론: 키 없으면 조용히 종료
        return

    print("OpenRouter 카탈로그 조회 중...", file=sys.stderr)
    all_models = fetch_models(api_key)
    sel = select_models(all_models)

    print(f"선택된 모델:", file=sys.stderr)
    for k, v in sel.items():
        print(f"  {k}: {v}", file=sys.stderr)

    changed_files: list[Path] = []
    diffs: list[str] = []

    changed, diff = patch_llm_client(sel)
    if changed:
        changed_files.append(ROOT / "src" / "llm_client.py")
        diffs.append(diff)

    changed, diff = patch_debate(sel)
    if changed:
        changed_files.append(ROOT / "src" / "hypothesis" / "multi_model_debate.py")
        diffs.append(diff)

    if not changed_files:
        print("[SILENT]")  # 크론: 변경 없으면 조용히 종료
        return

    # 변경 있을 때만 커밋 + 보고
    from datetime import date
    today = date.today().isoformat()
    commit_msg = (
        f"chore(models): OpenRouter 모델 자동 업데이트 ({today})\n\n"
        + "\n".join(f"- {Path(f).name}" for f in changed_files)
    )

    pushed = git_commit_push(changed_files, commit_msg)

    # 크론 보고 (Telegram으로 전달됨)
    print(f"## ab-lens OpenRouter 모델 업데이트 ({today})\n")
    print(f"변경 파일: {len(changed_files)}개")
    for f in changed_files:
        print(f"  - {Path(f).name}")
    print(f"\n최신 선택 모델:")
    print(f"  sonnet: {sel['sonnet_latest']}")
    print(f"  opus:   {sel['opus_latest']}")
    print(f"  haiku:  {sel['haiku_latest']}")
    print(f"  GPT:    {sel['gpt_latest']}")
    print(f"  Gemini: {sel['gemini_latest']}")
    print(f"\ngit push: {'✅' if pushed else '❌'}")
    if diffs:
        print("\n변경 내용 (주요):")
        for d in diffs:
            print(d[:500])


if __name__ == "__main__":
    main()
