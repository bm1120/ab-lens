"""골든셋 프롬프트 품질 회귀 (실LLM, @pytest.mark.golden).

각 시나리오를 N회(기본 5) 반복 실행하고, 불변속성을 ≥threshold(기본 4)회 충족하면 통과.
평소 테스트에서 제외(pyproject addopts `-m 'not golden'`). 수동: `pytest -m golden -s`.
CLAUDE_CODE_OAUTH_TOKEN 없으면 전체 skip.
"""
from __future__ import annotations

import pytest

from src.config import get_credential
from tests.golden.runner import evaluate, run_once
from tests.golden.scenarios import SCENARIOS

TOKEN = get_credential("CLAUDE_CODE_OAUTH_TOKEN")
N_RUNS = 5
THRESHOLD = 4

pytestmark = [
    pytest.mark.golden,
    pytest.mark.skipif(not TOKEN, reason="CLAUDE_CODE_OAUTH_TOKEN 없음 — 골든셋 skip"),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_golden_scenario(scenario):
    results = [run_once(scenario, TOKEN) for _ in range(N_RUNS)]
    res = evaluate(results, threshold=THRESHOLD)
    assert res.passed, (
        f"시나리오 '{scenario.id}' ({scenario.label}): "
        f"{N_RUNS}회 중 {res.hits}회 충족 (임계 {THRESHOLD}). 회차별={results}"
    )
