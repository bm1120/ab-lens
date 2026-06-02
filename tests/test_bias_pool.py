"""BIAS_REFERENCE_POOL — 설계 시점 편향 7종 레퍼런스 (하드코딩, enum 강제).

LLM이 풀 밖의 임의 편향을 지어내지 못하도록 BiasType(Literal)으로 구조적 차단.
풀 키와 Literal 값 집합이 항상 동기화돼야 한다.
"""
from typing import get_args

from src.bias_pool import BIAS_REFERENCE_POOL, BiasType


def test_pool_has_seven_biases():
    assert len(BIAS_REFERENCE_POOL) == 7


def test_each_entry_has_paper_and_mechanism():
    for key, entry in BIAS_REFERENCE_POOL.items():
        assert "paper" in entry and entry["paper"], key
        assert "mechanism" in entry and entry["mechanism"], key


def test_bias_type_literal_matches_pool_keys():
    # Literal 값 집합 == 풀 키 집합 (둘 중 하나만 바뀌면 실패 → 동기화 강제)
    assert set(get_args(BiasType)) == set(BIAS_REFERENCE_POOL.keys())
