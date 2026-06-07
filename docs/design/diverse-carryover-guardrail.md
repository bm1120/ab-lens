# diverse 초안 → 탭2 이월 가드레일 (확정 설계)

> 2026-06-07 준비. PR #15(개념→조작 정의화) 후속. 브랜치 `feat/diverse-carryover-guardrail`.
> ✅ **2026-06-07 brainstorming 확정**: 접근 **A(soft 경고) + C(플래그)**, 추상 판정은 **미확인 시 1회 재분류**.

## 배경 / 문제

PR #15에서 측정확인(개념→조작 정의화)을 **quality-loop·단순 경로에만** 적용하고,
**diverse(다양생성)는 "빠른 초안"으로 측정확인을 의도적으로 제외**했다.
→ diverse로 채택한 가설이 추상 구성개념(브랜드 인지도·신뢰 등)이어도,
   측정 타당도 미검증 상태로 탭2(결과분석)에 이월될 수 있다.

3-모델 P4 리뷰가 공통 지적:
- Gemini: "초안(Draft)→실행(Publish) 전이 시 검증 관문(state-transition guardrail) 부재".
- Codex: "측정확인 선택이 모든 downstream 경로에서 권위 있는 단일 계약으로 강제되지 않음".

## 가드레일 지점 (코드 위치, 2026-06-07 기준 app.py)

- **diverse 채택**: `app.py:547` adopt 버튼 → `QualityLoopResult` 조립 → `_store()` (측정확인 없음)
- **★ 탭2 이월 관문 = 설계 확정**: `app.py:726` "설계 확정 → 설계서 생성" 버튼
  → `assemble_design_context(hyp, bias, facts)` (`app.py:741`) → `design_context` → json 다운로드(`app.py:763`)
  → **이 시점이 모든 경로(diverse/단순/quality-loop) 공통의 "Publish" 관문.** 여기에 가드레일을 거는 게 가장 일관적.
- 측정확인 패널 재사용 가능: `measurement_pending` (`app.py:337`), `classify_construct`/`propose_measurement` import 됨.

## 접근 옵션 (brainstorming에서 확정)

- **A) soft 경고 (권장 출발점)**: 설계 확정 시 `classify_construct(hyp.sharpened_hypothesis)` → abstract/mixed인데
  측정확인 미경유면 경고 배지("⚠️ 측정 타당도 미확인 — 이 지표가 개념을 제대로 재나?") + [측정 확인하기] 바로가기 버튼.
  진행은 허용(hard 차단은 P3 리뷰 정신상 과함).
- **B) hard 게이트**: abstract면 측정확인 강제 후에만 설계 확정 허용. 마찰↑.
- **C) 출처 플래그**: `session_state['measurement_confirmed']`로 측정확인 경유 여부 추적 →
  미경유 + abstract일 때만 경고(중복 경고 방지). A와 결합 권장.

## 확정 설계 (2026-06-07)

**A + C, 미확인 시 1회 재분류.**

1. **순수 판정 헬퍼** `needs_measurement_warning(*, construct_kind, measurement_confirmed) -> bool`
   (`src/hypothesis/measurement.py`): `measurement_confirmed`면 False, 아니면 `construct_kind in (abstract, mixed)`.
   classify 실패는 `mixed`로 반환되므로(보수 편향) 자연히 경고 쪽 — 설계 의도와 일치.
2. **`measurement_confirmed` 플래그 수명** (`session_state`):
   - `_store()`가 항상 `False`로 **리셋** (모든 새 결과는 미확인에서 출발).
   - `_run_loop(..., pinned)`이 `_store` 직후 `measurement_confirmed = (pinned is not None)`로 덮어씀.
   - → 측정확인 패널에서 `confirm + primary`(pinned 생성) 경로만 True. **skip·diverse·simple·domain 경로는 모두 False** (skip도 미확인으로 경고 대상 — 의도된 동작).
3. **설계 확정(`app.py:726`) 게이트**: 미확인이면 `idea`를 `classify_construct` **1회** 호출 →
   `needs_measurement_warning`가 True면 soft 경고 배너 + `[측정 확인하기]` 바로가기.
   **설계서는 그대로 생성**(soft, 비차단). 바로가기는 기존 측정확인 라우팅(classify+propose→`measurement_pending`) 재사용.

판정 헬퍼는 순수 → 단위테스트. classify는 mock.

## 건드릴 파일

- `app.py`: 설계 확정 블록(726~) 가드레일, diverse `_store` 측정확인 플래그.
- 판정 로직은 작은 헬퍼(순수)로 분리 → 단위테스트.
- (선택) `tests/golden/`에 "diverse 추상 가설 이월 시 경고" 시나리오.

## TODO (진행 순서)

1. ~~brainstorming으로 접근 확정~~ ✅ **완료**: A+C, 미확인 시 1회 재분류.
2. 판정 헬퍼 `needs_measurement_warning` TDD (RED→GREEN).
3. 플래그 수명: `_store` 리셋 False + `_run_loop` pinned기반 set.
4. 설계 확정 블록 게이트: 1회 재분류 + soft 경고 배너 + 측정확인 바로가기.
5. app 구동 검증 + 전체 테스트 회귀.
6. 멀티모델 리뷰 1회 → 반영 → PR.
