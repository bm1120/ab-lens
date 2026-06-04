```markdown
# ab-lens 가설품질 스코어카드 설계안

## 설계 철학

가설 품질의 핵심은 **"이 실험을 돌렸을 때 무엇을 배울 수 있는가?"**이다. 
좋은 가설은 반증가능하고(Falsifiable), 인과경로가 명시되어 있으며(Causal), 
측정 가능하고(Measurable), 대안을 충분히 검토했다는(Comparative) 증거가 있어야 한다.

스코어카드는 **결정론적 체크(룰) 80% + 의미론적 검증(LLM) 20%** 비율로 구성하여 
재현성을 유지하면서도 질적 판단을 보완한다.

---

## 채점 차원 (총 100점)

| 차원 | 정의 | 가중치 | 판정방식 | HypothesisOutput 매핑 | 통과조건 |
|-----|------|--------|---------|---------------------|---------|
| **1. 구조적 완결성** | 필수 필드가 의미있게 존재하는가 | 20점 | 룰베이스 | `jtbd_reframe`, `mechanism_path`, `sharpened_hypothesis`, `suggested_primary_metric`, `experiment_feasible` | 5개 모두 비어있지 않음 + `experiment_feasible==True` → 20점, 1개 누락당 -4점 |
| **2. 인과 경로 구체성** | 개입→행동→지표 경로가 명확히 분해되었는가 | 25점 | 룰베이스 | `mechanism_path` | 세 단계(→ 2개) 구분 + 각 단계 15자 이상 → 25점. 단계 미분리 -15점, 단계당 15자 미만 -5점 |
| **3. 반증조건 명시성** | "어떤 결과면 가설이 틀렸다"가 명시되었는가 | 15점 | 룰베이스 + LLM | `sharpened_hypothesis`, `causal_alternative` | `causal_alternative` 존재 +10점. LLM이 hypothesis에서 반증조건 발견 +5점, 애매 +2점, 없음 0점 |
| **4. 측정 체계 정렬** | 지표가 가설-메커니즘과 정렬되었는가 | 15점 | 룰베이스 | `measurability_confirmed`, `suggested_secondary_metrics`, `predicted_tradeoff_metrics` | `measurability_confirmed==True` +7점, `secondary >= 1` +4점, `tradeoff >= 1` +4점 |
| **5. 대안 탐색 증거** | 다른 후보를 비교했다는 흔적이 있는가 | 10점 | 룰베이스 | `rejected_alternatives` | `len >= 2` → 10점, `1` → 5점, `0` → 0점 |
| **6. 편향 사전분석** | 주요 교란요인을 식별했는가 | 10점 | 룰베이스 | `confounder_candidates` | `len >= 3` → 10점, `2` → 6점, `1` → 3점, `0` → 0점 |
| **7. 가설 명료성** | 문장이 구체적·검증가능한가 | 5점 | LLM | `sharpened_hypothesis` | LLM 5점 척도: 명확+구체적(5), 이해가능(3), 모호(0~2) |

---

## 통과 기준 & 등급

| 총점 | 등급 | 조치 |
|-----|------|------|
| **85~100** | ✅ Experiment-Ready | 루프 종료, 다음 단계 진행 |
| **70~84** | ⚠️ Acceptable with Caveat | 통과하되 미달 차원을 사용자에게 경고 표시 |
| **50~69** | 🔄 Needs Refinement | sharpener 재호출 (피드백 주입) |
| **< 50** | ❌ Structural Failure | expander부터 재실행 권고 (또는 사용자에게 raw_idea 재입력 요청) |

**[가정]** 실무에서는 70점(Acceptable)도 통과시키되, 사용자에게 "편향 분석 부족" 같은 caveat를 명시하는 게 UX상 합리적. 85점 이상만 통과시키면 루프 과다.

---

## 루프 연동 설계

### 흐름
```
expander → sharpener → bias_screener → **[스코어카드 채점]**
└─ 85+ → 종료
└─ 70~84 → 통과 + 경고
└─ 50~69 → sharpener 재호출 (피드백 포함, 최대 2회)
└─ <50 → expander 재실행 또는 포기
```

### 피드백 신호 생성 (미달 차원 → sharpener에 주입)

각 차원이 임계값 미달이면 **구체적 개선 지시**를 생성하여 sharpener의 system prompt 또는 few-shot example에 추가.

| 미달 차원 | 피드백 템플릿 | sharpener 재호출 시 추가 지시 |
|----------|--------------|---------------------------|
| 인과 경로 구체성 < 20점 | "mechanism_path가 추상적입니다" | "mechanism_path를 '개입 → 사용자 심리/행동 변화(구체적) → 관측 지표'로 3단계 분해하고, 각 화살표 사이 연결고리를 15자 이상으로 명시하세요." |
| 반증조건 명시성 < 10점 | "가설이 틀렸을 조건이 불명확합니다" | "sharpened_hypothesis에 '만약 지표 X가 Y% 이상 변하지 않으면 가설 기각' 같은 반증 조건을 명시하거나, causal_alternative에 대립가설을 추가하세요." |
| 측정 체계 정렬 < 12점 | "지표 구성이 불충분합니다" | "secondary_metrics에 메커니즘 중간 단계를 측정할 지표(예: 클릭률, 체류시간)를 추가하고, tradeoff_metrics에 부작용 후보를 1개 이상 제시하세요." |
| 대안 탐색 < 8점 | "다른 후보와 비교 근거가 없습니다" | "rejected_alternatives에 '왜 다른 2개 후보보다 이 가설이 나은지' 근거를 추가하세요." |
| 편향 사전분석 < 7점 | "교란요인 분석이 부족합니다" | "confounder_candidates를 3개 이상 나열하고, 각각 '어떻게 통제/측정할지' 한 문장 추가하세요." |
| 가설 명료성 < 3점 | "문장이 모호하거나 지나치게 길다" | "sharpened_hypothesis를 주어-동사-목적어가 명확한 한 문장(50자 이내)으로 재작성하고, 예상 효과 크기나 방향을 포함하세요." |

**구현 예시 (Python pseudocode)**
```python
if score < 85:
    feedback_items = [
        f"- {dim.name}: {dim.feedback_template}. {dim.instruction}"
        for dim in dimensions if dim.score < dim.threshold
    ]
    refinement_prompt = f"""
이전 가설의 개선 필요 항목:
{chr(10).join(feedback_items)}

위 지적사항을 반영하여 가설을 재작성하세요.
"""
    refined = sharpener(prev_output, refinement_prompt)
```

---

## 무한루프 방지 정책

1. **최대 리파인 횟수**: 2회  
   - 3회 sharpener 호출(초기 1 + refine 2) 후에도 70점 미달이면 **강제 종료 + "가설 재설계 필요" 경고**

2. **정체 감지** (Plateau Detection)  
   - 연속 2회 점수 차이가 **절대값 5점 이하**면 "더 개선 어려움" 판단 → 현재 상태로 통과 또는 사용자 개입 요청

3. **차원별 하한선**  
   - 구조적 완결성 < 16점 (5개 중 2개 이상 누락) 또는 인과 경로 < 10점이면 **expander 재실행 트리거** (sharpener로는 복구 불가능한 구조적 결함)

4. **토큰 예산 상한** [가정]  
   - 전체 루프 누적 토큰이 50k 초과 시 경고 + 강제 종료 (비용 통제)

---

## 구현 위치

- **파일**: `src/hypothesis/quality_scorecard.py`
- **함수**:
  - `score_hypothesis(output: HypothesisOutput) -> ScorecardResult`  
    - 룰베이스 6개 차원 + LLM 1개 차원(병렬 또는 순차) → 총점 + 차원별 점수 + 미달 피드백 리스트 반환
  - `generate_refinement_feedback(scorecard: ScorecardResult) -> str`  
    - 미달 차원들의 피드백 템플릿 조합
- **스키마**: 
```python
@dataclass
class DimensionScore:
    name: str
    score: float
    max_score: float
    threshold: float  # 이 차원 단독 통과 기준
    feedback_template: str
    instruction: str  # sharpener 재호출용

@dataclass
class ScorecardResult:
    total_score: float
    dimensions: list[DimensionScore]
    grade: str  # "Experiment-Ready" | "Acceptable" | "Needs Refinement" | "Structural Failure"
    should_refine: bool
    refinement_feedback: str | None
```

---

## 룰베이스 vs LLM 선택 근거

| 차원 | 방식 | 이유 |
|-----|------|------|
| 구조적 완결성 | 룰 | 필드 존재 여부는 deterministic |
| 인과 경로 구체성 | 룰 | 문자열 길이 + 화살표 개수 = 기계적 측정 가능 |
| 반증조건 명시성 | 룰+LLM | `causal_alternative` 존재는 룰, "hypothesis 문장 안에 반증 조건 포함 여부"는 LLM |
| 측정 체계 정렬 | 룰 | 리스트 개수 + bool 플래그 = deterministic |
| 대안 탐색 증거 | 룰 | 리스트 개수 |
| 편향 사전분석 | 룰 | 리스트 개수 |
| 가설 명료성 | LLM | 주관적 판단 (구체성, 검증가능성) 필요 — **단, 5점 만점으로 제한하여 영향력 최소화** |

**LLM 채점 프롬프트 예시** (가설 명료성, 5점):
```
다음 가설 문장을 평가하세요:
"{sharpened_hypothesis}"

채점 기준 (0~5점):
5점: 주어/동사/목적어 명확 + 예상 효과 크기/방향 명시 + 반증 조건 포함
3점: 문장 이해 가능하나 수치/방향 모호
0점: 추상적이거나 검증 불가능

점수만 정수로 반환하세요.
```

---

## 독자적 차별화 포인트

1. **"Information Gain" 중심 설계**  
   - 단순 체크리스트가 아니라 "실험 후 배울 게 명확한가?"를 묻는 차원 배치 (인과경로 25점 최고 가중치)

2. **반증조건 명시성을 독립 차원으로**  
   - 대부분의 가설 품질 평가는 "구체성"만 보지만, Popper적 과학철학 관점에서 **"언제 틀렸다고 할 건가?"**를 명시하는 게 핵심

3. **적응적 통과 기준** (70점 Acceptable 등급)  
   - 현실에서는 완벽보다 "충분히 좋은" 지점에서 진행하는 게 합리적 — 85점만 강요하면 루프 과다 → 비용/시간 낭비

4. **차원별 하한선 + expander 재실행 트리거**  
   - 단순 총점이 아니라 **구조적 결함**(완결성 낮음, 인과경로 붕괴)은 sharpener로 못 고친다 → expander부터 다시 돌림

5. **정체 감지 (Plateau Detection)**  
   - 점수가 오르지 않으면 루프를 더 돌아도 소용없음 → 조기 종료로 비용 절감

---

## [가정] 명시

- LLM 채점 재현성: 같은 모델·temperature=0 기준 5점 체계는 ±1점 오차 가정
- 편향 최소 3개 기준: bias_screener가 보통 3~7개 반환한다고 가정
- rejected_alternatives >= 2: expander가 3후보 발산 → sharpener가 1개 선택 → 2개는 rejected에 들어간다고 가정
- 85점 임계값: 실험 진행 전 품질 게이트로서 "대부분 차원 양호" 기준 (7개 차원 평균 12/14 이상)
```
