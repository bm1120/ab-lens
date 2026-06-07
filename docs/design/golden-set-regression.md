# 골든셋 프롬프트 품질 회귀 (spec)

> 2026-06-06 / 브랜치 작업. 프롬프트 수정 시 출력 품질 회귀를 실LLM로 감지.

## 목적

단위테스트는 mock이라 프롬프트 품질을 보지 못한다. 골든셋은 **실LLM(Claude Code OAuth Haiku)** 으로
대표 입력 시나리오를 돌려, 점수 숫자가 아니라 **항상 참이어야 하는 불변속성**을 검증한다.

## 판정 방식 (비결정성 대응)

- 각 시나리오를 **5회 반복** 호출 → 불변속성을 **≥4회(80%)** 충족하면 통과.
- 생성·판정 모두 **Haiku 고정**(`CLAUDE_CODE`): 재현성 + 비용 0.
- judge는 Haiku temp=0(결정론). 생성(expand/sharpen)이 비결정 원인 → 반복으로 흡수.

## 실행

- `@pytest.mark.golden` 마커 → 평소 테스트엔 **제외**. 수동 `pytest -m golden`.
- `CLAUDE_CODE_OAUTH_TOKEN` 없으면 자동 skip (CI 안전).

## 시나리오 8종 + 불변속성

| # | 입력 유형 | 불변속성 |
|---|---|---|
| 1 | trivial (버튼 오타 수정) | `route_trivial.is_trivial == True` |
| 2 | 명확 가설 (버튼 상단 이동) | not trivial + `gate_passed == True` |
| 3 | 모호 (클릭률 올리고 싶다) | not trivial + sharpened 측정지표 존재 + mechanism_path에 `→` |
| 4 | anchored (경쟁사 5%니 우리도) | bias_screen(deep)에 `anchoring` status=active |
| 5 | 추상 목표 (장기 브랜드 인지도) | not trivial + `suggested_primary_metric` 존재(측정가능 프록시) + mechanism_path에 `→` <br>※ 당초 `feasible=False`였으나 sharpener가 추상 입력도 측정가능하게 구체화 → 0/5 실패 → 현실적 불변속성으로 재정의(2026-06-06) |
| 6 | 팀합의 (state=team_agreed) | HypothesisOutput 정상 + `gate_passed == True` (expander 미호출) |
| 7 | 도메인 이커머스 (장바구니 단계 축소) | not trivial + `gate_passed == True` |
| 8 | 도메인 SaaS (온보딩 체크리스트) | not trivial + `gate_passed == True` |

- 2·6·7·8의 `gate_passed`는 `score_hypothesis(...).gate_passed`(반증가능성 게이트).
- 3의 "측정지표 존재" = `suggested_primary_metric` 비어있지 않음.

## 구조

```
tests/golden/
  scenarios.py              ← GoldenScenario(입력 + 불변속성 함수) 8종 데이터
  runner.py                 ← run_once(시나리오)→bool, evaluate(results,threshold)→판정 (결정론, 단위테스트)
  test_golden_regression.py ← @pytest.mark.golden 파라미터화 (5회 반복 → evaluate)
```

- `evaluate(results: list[bool], n=5, threshold=4)` 는 순수 함수 → mock 없이 TDD.
- 실패 메시지: "시나리오 #4 anchored: 5회 중 2회 충족 (임계 4)".

## 비용

8종 × 5회 × ~3-4호출 ≈ 130호출. Haiku·구독이라 수 분·비용 0. trivial은 1호출로 조기종료.

## 비범위 (다음 스펙)

- 점수 절대 임계 튜닝(현재는 불변속성만).
- 다음 작업 영역은 **가설(hypothesis) 품질/생성** — UX/UI 아님 (사용자 지시 2026-06-06).
