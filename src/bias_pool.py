"""설계 시점 편향 레퍼런스 풀 (하드코딩).

BiasType(Literal)으로 LLM 출력이 이 7종을 벗어나지 못하게 구조적으로 강제한다.
풀 밖의 임의 편향을 지어낼 수 없다.
"""
from typing import Literal

BiasType = Literal[
    "confirmation_bias",
    "sunk_cost_fallacy",
    "anchoring",
    "p_hacking",
    "novelty_effect",
    "survivorship_bias",
    "causal_illusion",
]

BIAS_REFERENCE_POOL: dict[str, dict[str, str]] = {
    "confirmation_bias": {"paper": "Kahneman (2011) Ch.12", "mechanism": "선호 결과 지지 증거만 탐색"},
    "sunk_cost_fallacy": {"paper": "Kahneman (2011) Ch.32", "mechanism": "투입 비용이 의사결정에 영향"},
    "anchoring": {"paper": "Tversky & Kahneman (1974) Science 185", "mechanism": "최초 수치가 기준점"},
    "p_hacking": {"paper": "Simmons et al. (2011) Psych Sci 22", "mechanism": "유의한 p값 나올 때까지 반복"},
    "novelty_effect": {"paper": "Kohavi et al. (2020) Trustworthy", "mechanism": "신규 기능 일시적 관심"},
    "survivorship_bias": {"paper": "Kahneman (2011) Ch.11", "mechanism": "성공 사례만으로 추론"},
    "causal_illusion": {"paper": "Matute et al. (2015) Front Psychol", "mechanism": "공존을 인과로 오해"},
}
