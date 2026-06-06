"""골든셋 러너.

- evaluate: 결정론 판정 (5회 중 ≥threshold 충족 → 통과). 단위테스트 대상.
- run_once: 실LLM 1회 실행 → 시나리오 불변속성 충족 여부(bool). 예외는 False.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoldenResult:
    passed: bool
    hits: int
    total: int


def evaluate(results: list[bool], threshold: int = 4) -> GoldenResult:
    hits = sum(1 for r in results if r)
    total = len(results)
    return GoldenResult(passed=hits >= threshold, hits=hits, total=total)


def run_once(scenario, api_key: str) -> bool:
    """시나리오를 실LLM로 1회 실행하고 불변속성 충족 여부를 반환. 예외는 보수적으로 False."""
    try:
        return bool(scenario.check(api_key))
    except Exception:
        return False
