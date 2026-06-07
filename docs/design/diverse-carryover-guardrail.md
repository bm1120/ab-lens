# diverse 초안 → 탭2 이월 가드레일 (작업 준비 / spec 스텁)

> 2026-06-07 준비. PR #15(개념→조작 정의화) 후속. 브랜치 `feat/diverse-carryover-guardrail`.
> ⚠️ 이건 **착수 전 준비 메모**다. 구현 전 brainstorming으로 접근(soft/hard, 플래그 방식)을 확정할 것.

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

## 권장 (착수 시 재확인)

- A + C: 설계 확정 시 "측정확인 미경유 + 추상" → soft 경고 + 측정확인 바로가기. 차단 안 함.
- `measurement_confirmed` 플래그는 `_run_loop`에서 pinned가 있었을 때 set, diverse `_store`에선 unset.
- 골든/단위 테스트: 가드레일 판정 로직(미경유+abstract→경고)을 순수 함수로 분리해 TDD.

## 건드릴 파일

- `app.py`: 설계 확정 블록(726~) 가드레일, diverse `_store` 측정확인 플래그.
- 판정 로직은 작은 헬퍼(순수)로 분리 → 단위테스트.
- (선택) `tests/golden/`에 "diverse 추상 가설 이월 시 경고" 시나리오.

## TODO (컴팩트 후 착수 순서)

1. brainstorming으로 A/B/C + 플래그 방식 확정 (사용자 확인).
2. 가드레일 판정 헬퍼 TDD → 설계 확정 블록 연결.
3. diverse `_store`/quality-loop pinned 경로에 `measurement_confirmed` 플래그.
4. app 구동 검증 + (선택) 골든 시나리오.
5. 멀티모델 리뷰 1회 → 반영 → PR.
