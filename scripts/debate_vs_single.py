#!/usr/bin/env python
"""debate vs single 점수 분포 검증 스크립트.

목적: 멀티모델 토론(diverse 3롤) vs 단일모델 single 실행의
     스코어카드 점수(0~100) + 게이트 통과율을 비교해
     "토론이 정말 단일모델보다 나은가"를 실데이터로 판단한다.

사용:
    uv run python scripts/debate_vs_single.py
    uv run python scripts/debate_vs_single.py --runs 3 --out results/debate_check.json

출력:
    - 시나리오별 single/debate 점수 테이블
    - 전체 평균 delta (debate - single)
    - 결론: WORTH_IT / MARGINAL / NOT_WORTH_IT
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 하위에서 실행 시)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_credential
from src.schemas import LLMProvider
from src.hypothesis.pipeline import run_hypothesis_pipeline
from src.hypothesis.quality_scorecard import judge_hypothesis, score_hypothesis
from src.hypothesis.diverse_generator import generate_diverse, available_providers

TOKEN: str = get_credential("CLAUDE_CODE_OAUTH_TOKEN") or ""
PROVIDER = LLMProvider.CLAUDE_CODE


# ── 비교 대상 시나리오 (골든셋 아이디어 재활용, 단 점수 측정용) ──────────
SCENARIOS = [
    ("vague",        "클릭률을 올리고 싶다"),
    ("clear",        "결제 버튼을 결제 페이지 상단으로 옮기면 체크아웃 전환율이 오른다"),
    ("abstract",     "브랜드 인지도를 높이면 장기적으로 전체 매출이 늘어날 것이다"),
    ("ecommerce",    "장바구니 결제 단계를 3단계에서 1단계로 줄이면 구매 전환율이 오른다"),
    ("saas",         "신규 가입자에게 온보딩 체크리스트를 제공하면 7일 내 활성화율이 오른다"),
    ("anchored",     "경쟁사가 가격을 5% 올렸으니 우리도 정확히 5% 올리면 매출이 유지될 것이다"),
]


@dataclass
class RunResult:
    scenario_id: str
    mode: str          # "single" | "debate"
    score: int | None  # None = 실패
    gate_passed: bool | None
    elapsed_s: float
    error: str | None = None


def run_single(scenario_id: str, idea: str) -> RunResult:
    """단일모델(Quick) 실행 후 스코어카드 점수 반환."""
    t0 = time.monotonic()
    try:
        r = run_hypothesis_pipeline(
            idea, mode="quick", hypothesis_state="initial_idea",
            api_key=TOKEN, provider=PROVIDER, lang="ko",
        )
        if r.trivial or r.hypothesis is None:
            return RunResult(scenario_id, "single", None, None,
                             time.monotonic() - t0, "trivial or no hypothesis")
        j = judge_hypothesis(r.hypothesis, api_key=TOKEN, provider=PROVIDER)
        sc = score_hypothesis(r.hypothesis, j)
        return RunResult(scenario_id, "single", sc.total, sc.gate_passed,
                         time.monotonic() - t0)
    except Exception as e:
        return RunResult(scenario_id, "single", None, None,
                         time.monotonic() - t0, repr(e))


def run_debate(scenario_id: str, idea: str) -> RunResult:
    """멀티롤 diverse(현재 토론 구현) 실행 후 best candidate 점수 반환."""
    t0 = time.monotonic()
    try:
        providers = available_providers(PROVIDER, TOKEN)
        result = generate_diverse(
            idea,
            providers=providers,
            lang="ko",
            mode="quick",
        )
        if not result.candidates:
            return RunResult(scenario_id, "debate", None, None,
                             time.monotonic() - t0, "no candidates")
        # 랭킹 1위(게이트통과+최고점) 채택
        best = result.candidates[0]
        return RunResult(scenario_id, "debate", best.scorecard.total,
                         best.scorecard.gate_passed, time.monotonic() - t0)
    except Exception as e:
        return RunResult(scenario_id, "debate", None, None,
                         time.monotonic() - t0, repr(e))


def fmt_score(r: RunResult) -> str:
    if r.score is None:
        return f"ERR({r.error[:30] if r.error else '?'})"
    gate = "✅" if r.gate_passed else "❌"
    return f"{gate} {r.score:3d}pt ({r.elapsed_s:.1f}s)"


def verdict(delta: float) -> str:
    if delta >= 5:
        return "WORTH_IT    ✅  토론이 유의미하게 점수를 올렸다 (≥5pt)"
    if delta >= 0:
        return "MARGINAL    🟡  토론이 미미하게 나음 (0~5pt) — 비용 대비 재검토"
    return "NOT_WORTH_IT ❌  토론이 단일모델보다 낮거나 같음 — 파이프라인 재설계 필요"


def main():
    parser = argparse.ArgumentParser(description="debate vs single 점수 분포 검증")
    parser.add_argument("--runs", type=int, default=2,
                        help="시나리오당 반복 횟수 (기본 2 — 비용/시간 절충)")
    parser.add_argument("--out", type=str, default=None,
                        help="결과를 JSON으로 저장할 경로 (선택)")
    args = parser.parse_args()

    if not TOKEN:
        print("❌ CLAUDE_CODE_OAUTH_TOKEN 없음 — ~/.hermes/.env 확인")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  debate vs single 검증  (시나리오 {len(SCENARIOS)}개 × {args.runs}회)")
    print(f"{'='*60}\n")

    all_results: list[RunResult] = []
    deltas: list[float] = []

    for sid, idea in SCENARIOS:
        print(f"📋 [{sid}] {idea[:50]}...")
        s_scores, d_scores = [], []

        for run in range(args.runs):
            print(f"   run {run+1}/{args.runs}", end=" ", flush=True)

            sr = run_single(sid, idea)
            dr = run_debate(sid, idea)
            all_results.extend([sr, dr])

            print(f"single={fmt_score(sr)}  debate={fmt_score(dr)}")

            if sr.score is not None:
                s_scores.append(sr.score)
            if dr.score is not None:
                d_scores.append(dr.score)

        s_avg = statistics.mean(s_scores) if s_scores else None
        d_avg = statistics.mean(d_scores) if d_scores else None

        if s_avg is not None and d_avg is not None:
            delta = d_avg - s_avg
            deltas.append(delta)
            sign = "+" if delta >= 0 else ""
            print(f"   → 평균 single={s_avg:.1f}  debate={d_avg:.1f}  delta={sign}{delta:.1f}pt")
        else:
            print(f"   → 점수 없음 (오류)")
        print()

    # ── 전체 집계 ──
    print(f"{'='*60}")
    print("  전체 결과")
    print(f"{'='*60}")

    if deltas:
        overall = statistics.mean(deltas)
        sign = "+" if overall >= 0 else ""
        print(f"\n  전체 평균 delta: {sign}{overall:.1f}pt  (양수=debate가 높음)")
        print(f"  시나리오별 delta: {[f'{sign}{d:.1f}' if (sign:=('+' if d>=0 else '')) else f'{d:.1f}' for d in deltas]}")
        print(f"\n  결론: {verdict(overall)}\n")
    else:
        print("\n  ❌ 유효한 결과 없음 — 모든 시나리오 오류\n")

    # ── JSON 저장 ──
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "runs_per_scenario": args.runs,
            "overall_delta": statistics.mean(deltas) if deltas else None,
            "verdict": verdict(statistics.mean(deltas)) if deltas else "NO_DATA",
            "results": [asdict(r) for r in all_results],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"  💾 결과 저장: {out_path}")


if __name__ == "__main__":
    main()
