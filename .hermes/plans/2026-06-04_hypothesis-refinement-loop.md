# ab-lens: 가설 고도화 멀티턴 정제 루프 설계

> 작성일: 2026-06-04  
> 목표: "일반 LLM에 질문한 것과 동일하다"는 문제 해소 → 품질 스코어가 통과될 때까지 멀티턴으로 가설을 반복 정제하는 구조

---

## 핵심 아이디어 요약

현재 문제: 아이디어 입력 → LLM 한 방 → 결과 출력. 사용자 맥락 없이 범용 답변과 다를 게 없음.

해결 방향:
1. **서비스 컨텍스트 수집 (2번)**: 서비스/도메인 정보가 없으면 먼저 질문으로 채운다
2. **품질 스코어카드 (3번)**: 4축 점수가 임계값 미달이면 루프 계속
3. **멀티턴 소크라테스 정제 (1번 + 4번)**: 약한 축을 집중 공격하는 targeted 재실행

---

## 새로운 탭1 플로우

```
[Phase 0] 서비스 컨텍스트 체크
  → ServiceContext가 session_state에 없으면?
     → LLM이 서비스 파악 질문 3~5개 생성
     → 사용자가 채팅 형식으로 답변
     → 답변 완료 → ServiceContext 구성 → Phase 1로

[Phase 1] 가설 입력
  → 기존과 동일: idea text_area + Quick/Deep 선택

[Phase 2] 파이프라인 실행 (기존 + 컨텍스트 주입)
  → trivial_router → expander → sharpener → bias_screener
  → 단, 모든 프롬프트에 ServiceContext 주입

[Phase 3] 품질 스코어카드 계산
  → 4축 평가: 명확성 / 메커니즘 / 측정가능성 / 편향위험
  → 각 축 0~100점, 가중 합산
  → 임계값(기본 70점) 미달 시 → Phase 4
  → 통과 시 → Phase 5 (기존 설계 파라미터 단계)

[Phase 4] Targeted Refinement (약한 축 집중 공격)
  → 점수 낮은 축 상위 1~2개 식별
  → 해당 축 전용 소크라테스 질문 1~2개 생성
  → 사용자 답변 → 해당 축만 재실행 (전체 파이프라인 재실행 X)
  → Phase 3으로 돌아가서 재평가
  → 최대 3라운드 제한 (무한루프 방지)

[Phase 5] 기존 설계 파라미터 + 설계서 (현행 유지)
```

---

## 새로운 컴포넌트

### 1. `ServiceContext` (src/design_schemas.py 추가)
```python
class ServiceContext(BaseModel):
    service_name: str
    target_users: str          # 주요 사용자 세그먼트
    primary_metric: str        # 서비스의 핵심 북극성 지표
    current_baseline: str      # 현재 수치 수준 (대략적)
    past_experiments: str      # 과거 실험 결과 요약 (없으면 "없음")
    domain_constraints: str    # 도메인 특수 제약 (의료/금융 등)
```

### 2. `ContextCollector` (src/hypothesis/context_collector.py 신규)
- `generate_questions(idea, lang, model)` → LLM이 이 아이디어를 검증하려면 어떤 서비스 정보가 필요한지 질문 3~5개 생성
- `parse_answers(questions, answers)` → 답변을 ServiceContext로 구조화
- 채팅 메시지 형식으로 st.chat_message UI에 연결

### 3. `HypothesisScorer` (src/hypothesis/scorer.py 신규)
```python
class QualityScore(BaseModel):
    clarity: int           # 명확성: 가설이 구체적으로 서술됐는지 (0~100)
    mechanism: int         # 메커니즘: 개입→행동→지표 경로가 명시됐는지 (0~100)
    measurability: int     # 측정가능성: 지표가 실제 측정 가능한지 (0~100)
    bias_risk: int         # 편향위험 (낮을수록 좋음, 역산): 100 - bias_score (0~100)
    total: int             # 가중 합산: clarity*0.2 + mechanism*0.3 + measurability*0.3 + bias_risk*0.2
    weak_axes: list[str]   # total < threshold인 축 이름들
    passed: bool           # total >= threshold (기본 70)
    rationale: str         # LLM이 판단한 점수 근거 한 줄 요약
```
- `score_hypothesis(hypothesis_output, service_context, lang, model)` → LLM 호출로 채점
- deterministic 규칙으로 사전 필터 (mechanism_path 없으면 mechanism=0 등)

### 4. `RefinementAgent` (src/hypothesis/refinement_agent.py 신규)
- `generate_targeted_questions(weak_axes, hypothesis, service_context, lang, model)` → 약한 축에 집중한 소크라테스 질문 1~2개
- `refine_axis(axis, user_answer, hypothesis, service_context, lang, model)` → 해당 축만 재실행해서 HypothesisOutput 업데이트

---

## UI 변경 (app.py)

### Phase 0 — 컨텍스트 수집 UI
```
st.session_state["service_context"] 없으면:
  st.info("서비스 컨텍스트가 없어요. 몇 가지 질문에 답해주세요.")
  
  # 채팅 형식
  for q in generated_questions:
      st.chat_message("assistant").write(q)
  
  for i, q in enumerate(questions):
      answers[i] = st.text_input(q, key=f"ctx_q_{i}")
  
  [컨텍스트 저장] 버튼 → service_context 구성
  [건너뛰기] 버튼 → service_context = None (범용 모드)
```

### Phase 3 — 스코어카드 UI
```
st.metric("가설 품질", f"{score.total}/100")

col1, col2, col3, col4 = st.columns(4)
col1.metric("명확성", score.clarity)
col2.metric("메커니즘", score.mechanism)
col3.metric("측정가능성", score.measurability)
col4.metric("편향위험", score.bias_risk)

if not score.passed:
    st.warning(f"약한 축: {score.weak_axes} → 정제 라운드 진행")
    [정제 시작] 버튼
else:
    st.success("품질 기준 통과 → 설계 파라미터 단계로")
    [설계 진행] 버튼
```

### Phase 4 — 소크라테스 정제 UI
```
# 라운드 카운터 표시 (최대 3라운드)
st.caption(f"정제 라운드 {round}/3 — {weak_axes} 개선 중")

# 채팅 형식 질문
st.chat_message("assistant").write(targeted_question)
user_answer = st.text_input("답변", key=f"refine_r{round}")

[이 답변으로 재실행] 버튼 → refine_axis → re-score → Phase 3
```

---

## session_state 키 추가

| 키 | 타입 | 설명 |
|---|---|---|
| `service_context` | `ServiceContext \| None` | 서비스 맥락 |
| `ctx_questions` | `list[str]` | 컨텍스트 수집 질문 목록 |
| `quality_score` | `QualityScore` | 현재 가설 품질 점수 |
| `refinement_round` | `int` | 현재 정제 라운드 (0~3) |
| `refinement_history` | `list[dict]` | 라운드별 점수 변화 기록 |
| `targeted_questions` | `list[str]` | 현재 라운드 소크라테스 질문 |

---

## 파일 변경 목록

| 파일 | 변경 |
|---|---|
| `src/design_schemas.py` | `ServiceContext`, `QualityScore` 모델 추가 |
| `src/hypothesis/context_collector.py` | 신규: 컨텍스트 수집 에이전트 |
| `src/hypothesis/scorer.py` | 신규: 품질 스코어카드 |
| `src/hypothesis/refinement_agent.py` | 신규: targeted 정제 에이전트 |
| `src/hypothesis/pipeline.py` | ServiceContext 주입 파라미터 추가 |
| `src/hypothesis/expander.py` | ServiceContext 프롬프트 주입 |
| `src/hypothesis/sharpener.py` | ServiceContext 프롬프트 주입 |
| `app.py` | Phase 0/3/4 UI 추가, render_design_tab 재구성 |
| `tests/` | scorer, context_collector, refinement_agent 단위 테스트 |

---

## 구현 태스크 (브랜치: feat/hypothesis-refinement-loop)

- [ ] Task A: 스키마 추가 (`ServiceContext`, `QualityScore`)
- [ ] Task B: `context_collector.py` — 질문 생성 + 답변 파싱
- [ ] Task C: `scorer.py` — deterministic 사전 필터 + LLM 채점
- [ ] Task D: `refinement_agent.py` — 약한 축 질문 + targeted 재실행
- [ ] Task E: `pipeline.py` — ServiceContext 주입
- [ ] Task F: `app.py` — Phase 0/3/4 UI 조립
- [ ] Task G: 테스트 (mock LLM 기반 단위 테스트)

---

## 품질 임계값 기본값

| 축 | 가중치 | 개별 임계값 | 설명 |
|---|---|---|---|
| 명확성 | 20% | 60 | 가설이 구체적 대상/변화를 명시하는가 |
| 메커니즘 | 30% | 70 | 개입→행동→지표 경로가 논리적인가 |
| 측정가능성 | 30% | 70 | 제안 지표가 실제 수집 가능한가 |
| 편향위험 | 20% | 60 | 설계 시점 편향이 낮은가 (역산) |
| **종합** | — | **70** | 가중 합산 기준 |

---

## 오픈 이슈

1. **컨텍스트 저장 범위**: session_state만? 아니면 `ab-design-context.json`에 포함?  
   → 일단 session_state + DesignContext 이월 시 포함 권장
2. **스코어링 비용**: LLM 채점 vs deterministic 규칙  
   → 1차: deterministic 규칙으로 mechanism/measurability 판단, 2차: LLM으로 clarity/bias_risk 채점
3. **정제 라운드 상한**: 3라운드 고정 vs 사용자 설정  
   → 일단 3 고정, 사이드바에서 조절 가능하게 추후 확장
