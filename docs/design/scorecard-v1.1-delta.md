# HQS v1.1 설계 델타 — T1a 진단 반영 + 룰가이드 LLM judge

> HQS v1(`docs/design/hypothesis-quality-scorecard.md`) 대비 구현(`src/hypothesis/quality_scorecard.py`)에서 바뀐 점. PR #4 리뷰 + T1a 진단의 결과.

## T1a 진단 결과 (다양한 가설 18개, multi-provider+롤 생성 → 파이프라인 fill-rate)
- **§8.2 "REDESIGN 폭증" 리스크 = 기우**: 모든 list 필드 empty율 0%, `measurability_confirmed`/`experiment_feasible` 100% True.
- **⚠️ 개수 ≠ 품질**: 모호 vs 구체 입력의 list 필드 개수가 **거의 동일**(confounder 5.2 vs 5.4, tradeoff 3.3 vs 3.7, secondary 4.8 vs 5.4). expander가 입력 품질과 무관하게 채운다 → **개수 세기는 변별력 0**.

## 반영한 변경
| 항목 | v1 (설계) | v1.1 (구현) | 이유 |
|---|---|---|---|
| **D4 측정정렬·리스크** | 개수 가산(secondary/tradeoff/confounder count) | **LLM 관련성 판정**(confound_relevant Y/P/N + tradeoff_real Y/N), list 비면 0 | 개수는 항상 채워져 변별력 없음(진단) |
| **D5 대안탐색** | rejected 개수 | **LLM alt_justified**(실질 사유 여부) | 동상 |
| **D1 게이트** | `measurability_confirmed==True` AND 지표명 | **지표명 모호성 룰만**(플래그는 100% True라 무용) | 진단: 플래그 변별력 0 |
| **LLM judge** | Y/P/N 판정 | **룰 가이드** — 각 판정에 결정 규칙+체크리스트 프롬프트(`JUDGE_PROMPT`) | 자유판단 금지 → 재현성(§8.3) |
| **i18n** | 한국어 하드코딩 | **lang별 렉시콘(ko/en)** `scorecard_lexicons.py` | PR #4 🔴 Blocker 해소 |
| **절대임계 80/68** | 코드가 하드 사용 | **봉인(기본 비활성)** `ABS_THRESHOLDS_ENABLED=False`, 게이트+상대등급으로 출발 | 매직넘버 캘리브레이션 전 봉인 일관화 |

## 룰 가이드 LLM judge (당신 요청)
LLM이 점수를 만들지 않고, **각 차원 Y/P/N에 명시적 판정 규칙**을 따른다:
- falsifiable: '틀렸다 관측 1문장' 가능할 때만 Y
- mechanism: 화살표 하나씩 검사 (전부 인과=Y / 한 링크 가정=P / 누락·상관=N)
- confound_relevant: 처치배정 AND 지표 둘 다 영향 ≥2개=Y
- tradeoff_real / alt_justified: 실재·실질사유 기준

## 구현 모듈
- `scorecard_lexicons.py` — lang별 렉시콘(i18n)
- `scorecard_schemas.py` — `LLMJudgment`(룰가이드 판정), `ScorecardResult`
- `quality_scorecard.py` — 룰 차원 + `judge_hypothesis`(룰가이드) + `score_hypothesis` + `should_stop`(Best-so-far)
- `feedback_generator.py` — 미달 차원 → sharpener 피드백(lang별)
- `tests/test_quality_scorecard.py` — 19 케이스 (룰 결정론 + 등급 + i18n + 정체)

## 봉인/후속 (정직성)
- 절대임계 80/68, D6 모호어밀도 0.18 = 캘리브레이션 전 잠정값 → 운영 로그로 ROC 재조정.
- LLM 이진 판정 재현성(같은 가설 2회 일치율) 측정은 T1c.
- 루프 연동(sharpener 재호출 실제 배선)은 T3.
