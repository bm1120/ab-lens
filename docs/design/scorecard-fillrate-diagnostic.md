# T1a 진단 — HypothesisOutput 필드 fill-rate

> 다양한 가설 18개(multi-provider+롤로 생성: Claude/GPT/Gemini × 도메인 2롤 × 품질혼합)를
> ab-lens 파이프라인(provider=CLAUDE_CODE, mode=quick)에 통과시켜 측정. 스코어카드 설계 교정용.

## 결과
- **모든 list/str 필드 empty율 0%**, `measurability_confirmed`·`experiment_feasible` **100% True**.
- 18건 전부 처리(trivial/error 0).

| 필드 | mean | empty율 |
|---|---|---|
| confounder_candidates | 5.3 | 0% |
| rejected_alternatives | 2.5 | 0% |
| predicted_tradeoff_metrics | 3.6 | 0% |
| suggested_secondary_metrics | 5.2 | 0% |
| implicit_assumptions | 5.6 | 0% |

## 핵심 발견 — 개수 ≠ 품질
| 필드 | 모호입력 | 구체입력 | 판정 |
|---|---|---|---|
| confounder_candidates | 5.2 | 5.4 | ≈같음 |
| predicted_tradeoff_metrics | 3.3 | 3.7 | ≈같음 |
| suggested_secondary_metrics | 4.8 | 5.4 | ≈같음 |
| implicit_assumptions | 5.8 | 5.4 | ≈같음 |
| rejected_alternatives | 2.0 | 2.8 | 약하게 구체↑ |
| mechanism_path(길이) | 106 | 114 | 약하게 구체↑ |

→ expander가 입력 품질과 무관하게 필드를 채운다. **개수 세기는 변별력 없음** → D4·D5를 개수→LLM 관련성 판정으로 전환(v1.1 델타).
→ §8.2 "빈 배열로 REDESIGN 폭증" 리스크는 **기우**(empty율 0%).
