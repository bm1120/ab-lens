# 개념적 → 조작적 정의화 (측정 타당도) — spec

> 2026-06-07. 3-모델 리뷰(Gemini/Codex/Claude) 반영 최종안.
> 관련: `hypothesis/` 파이프라인, `design_schemas.py`, 탭1 UI.

## 배경 / 문제

추상 구성개념(construct) 입력 — 예 "브랜드 인지도를 높이면 장기 매출↑" — 을 주면 현 `sharpener`가
즉시 `CAC:LTV ≥ 3:1` 같은 지표를 **사용자·도메인 확인 없이 독단 선택**한다. 측정 타당도(이 지표가
정말 그 개념을 재는가?)를 건너뛰고, "수치=사용자 입력" 철학과 어긋난다.

해결: 사회과학 측정이론(conceptualization → operationalization)을 **추상 개념 감지 시에만** 삽입.

## 3-모델 리뷰에서 확정된 제약 (원안 대비 변경)

1. **2게이트+멀티턴 위저드 폐기 → 단일 "측정 확인" 패널**. (Streamlit session_state 위저드는
   1인 MVP에 과부담·이탈·rerun 상태손실 — Gemini RETHINK, Codex GO-with-cuts 공통)
2. 감지 = **clear / abstract / mixed 3분류** + 근거를 **사용자에게 표시**. 불확실하면 측정확인 쪽으로
   편향(거짓음성이 거짓양성보다 비용 큼).
3. **🔑 탭1↔탭2 정합 제약**: 탭2 통계엔진은 `proportion / continuous / count`만 분석한다. 지표 후보는
   이 3종에 매핑되는 **행동지표만 기본 노출**. 설문/시계열/장기·크로스채널 귀인 지표는
   "A/B 직접 측정 부적합 + 인과대안" 으로 **분리 표시(제외+경고 하이브리드)**.
4. 사용자 확정 지표가 sharpener를 **실제로 구속(고정 주입)** 해야 "선택의 착시"가 아니다.

## 흐름

```
아이디어 → trivial_router → expander(발산)
  → classify_construct(idea) → {clear | abstract | mixed} + constructs + 근거
       ├─ clear         → 기존 sharpener 직행 (빠른 경로, 변화 없음)
       └─ abstract|mixed → [측정 확인 패널 — 단일 화면]
              · 감지 알림 표시 ("추상 구성개념 감지: 신뢰, 인지도")
              · 구성개념별: 개념적 정의(인라인 편집) + 지표 후보(객관식+기타, 탭2 호환만)
              · 비호환 지표: "⚠️ A/B 직접 측정 부적합" 참고 섹션 + 인과대안
              · "모르겠음" 선택 시에만 1회 심층 질문(객관식+기타)
              · [이 측정으로 계속] / [측정 확인 건너뛰기]
  → sharpen(..., pinned_metrics=확정지표)   # 지표 고정, LLM은 메커니즘·수렴만
  → HypothesisOutput → DesignContext
```

## 모듈 / 스키마

```
src/hypothesis/
  classify.py      ← classify_construct(idea, ...) -> ConstructClassification
  measurement.py   ← propose_measurement(idea, constructs, domain_ctx, ...) -> MeasurementProposal
  sharpener.py     ← sharpen(..., pinned_metrics: Optional[PinnedMetrics] = None) 확장
```

```python
ConstructKind = Literal["clear", "abstract", "mixed"]

class ConstructClassification(BaseModel):
    kind: ConstructKind
    constructs: list[str]          # 식별된 구성개념 (clear면 빈 리스트 가능)
    rationale: str                 # 사용자에게 보여줄 근거 1~2문장
    # 불확실 시 LLM이 mixed로 — 호출부는 mixed를 측정확인 쪽으로 라우팅

class MetricCandidate(BaseModel):
    label: str
    metric_type: Literal["proportion", "continuous", "count"]  # 탭2 호환 3종만
    ab_testable: bool = True       # False면 분리 표시(설문/장기 등)
    rationale: str

class ConstructMeasurement(BaseModel):
    construct: str
    conceptual_definition: str     # 편집 가능
    candidates: list[MetricCandidate]
    incompatible_note: str = ""    # 비호환 지표·인과대안 안내(있을 때)

class MeasurementProposal(BaseModel):
    measurements: list[ConstructMeasurement]
    needs_question: bool = False   # 도메인 부족 → "모르겠음" 경로용
    question: str = ""

class PinnedMetrics(BaseModel):    # 사용자 확정 → sharpener 주입
    primary_metric: str
    secondary_metrics: list[str] = []
```

- `propose_measurement`는 후보 `metric_type`을 3종으로 **강제**(Literal). 설문/시계열은
  `ab_testable=False`로 표시하고 `incompatible_note`에 인과대안.

## UI (단일 Streamlit, session_state 최소)

- 탭1 가설 고도화 버튼 → `classify_construct`.
- `clear` → 기존 흐름.
- `abstract|mixed` → `st.session_state["measure_stage"]="confirm"` → **측정 확인 패널** 1장:
  - 구성개념별 `text_area`(정의 편집) + `radio`(호환 후보) + "기타" `text_input`.
  - 비호환 지표는 `st.expander("⚠️ A/B 직접 측정 부적합")` 로 분리.
  - 확정 → `PinnedMetrics` → `sharpen(pinned_metrics=...)` → 결과.
- 위저드(다단계 모달) 없음. 한 화면에서 편집·확정. rerun 안전(입력은 위젯 key로 보존).

## sharpener 고정 주입

```python
def sharpen(..., pinned_metrics: PinnedMetrics | None = None):
    out = call_structured(...)               # 메커니즘·수렴·기각대안
    if pinned_metrics:                        # 지표는 사용자 확정값으로 덮어씀(LLM 재선택 금지)
        out = out.model_copy(update={
            "suggested_primary_metric": pinned_metrics.primary_metric,
            "suggested_secondary_metrics": pinned_metrics.secondary_metrics,
        })
    return out.model_copy(update={"raw_idea": idea})
```

## 검증

- `classify_construct`: TDD mock — clear/abstract/mixed 분기, 불확실→mixed.
- `propose_measurement`: TDD mock — 스키마, `metric_type` 3종 강제, 비호환은 `ab_testable=False`.
- `sharpen(pinned_metrics=...)`: TDD — 확정 지표가 LLM 출력을 덮어쓰는지.
- 골든셋 `abstract_proxy` 강화: classify=abstract|mixed + 개념정의 산출 + 후보 `metric_type`이 3종.

## 구현 페이즈 (각 페이즈: TDD → 커밋 → 멀티모델 리뷰 반영 → 커밋)

- **P1 측정 코어**: `classify.py`(3분류) + `measurement.py`(개념정의·지표후보) + 스키마. TDD mock + 실LLM 스모크.
- **P2 파이프라인 통합**: `sharpener` pinned 주입 + `pipeline` classify 라우팅(clear=빠른경로). TDD + e2e.
- **P3 측정 확인 패널 UI**: 단일 Streamlit 패널, session_state, 탭2 정합 분리표시. app 구동 검증.
- **P4 검증**: 골든셋 `abstract_proxy` 강화(classify/measurement 시나리오) + 실LLM 골든 통과.
- **P5 스킬화**: P1~P4에서 반복한 멀티모델 리뷰 워크플로를 `~/.claude/skills/multi-model-review`로 패키징.
- 종료: feature 브랜치 → **PR 생성**(머지는 사용자 확인 후).

## 비범위 (YAGNI)

- 완전 멀티턴 위저드(폐기).
- 탭2에 설문/시계열 분석엔진 추가(별도 — 지금은 호환 3종으로 제약해 회피).
- 측정 윈도우/지연 정밀 feasibility 엔진(지금은 `ab_testable` 플래그 + 경고로 경량 처리).
