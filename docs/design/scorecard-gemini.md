### 1. 가설 품질 차원 (Hypothesis Quality Dimensions)

가능한 한 `HypothesisOutput`의 필드 유무와 구조를 검증하는 룰베이스에 높은 가중치를 부여하고, 논리의 타당성을 검증하는 주관적 영역에만 LLM 채점을 제한합니다.

| 차원 (Dimension) | 정의 | 가중치 | 판정방식 (Rule/LLM) | HypothesisOutput 매핑 필드 | 통과조건 (Criteria) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. 구조적 완전성 (Completeness)** | 가설 검증을 위한 필수 데이터/지표가 모두 정의되었는가? | **25%** | **Rule** | `measurability_confirmed`, `suggested_primary_metric` | `measurability_confirmed == True` AND `primary_metric` 존재 (길이 > 0) |
| **2. 메커니즘 구체성 (Mechanism)** | '개입→행동→지표'의 인과 경로가 구조적으로 명시되었는가? | **20%** | **Rule** | `mechanism_path` | `mechanism_path` 내에 최소 2개 이상의 화살표(또는 [가정] 리스트 노드 3개 이상) 존재 |
| **3. 리스크 인지 (Risk Awareness)** | 성공 지표 외에 부작용이나 교란 변수를 고려했는가? | **15%** | **Rule** | `predicted_tradeoff_metrics`, `confounder_candidates` | `tradeoff_metrics` 길이 $\ge$ 1 AND `confounder_candidates` 길이 $\ge$ 1 |
| **4. 대안적 사고 (Alternative)** | 초기 아이디어 외의 인과적 대안을 탐색했는가? | **10%** | **Rule** | `rejected_alternatives`, `causal_alternative` | `rejected_alternatives` 길이 $\ge$ 1 OR `causal_alternative` 존재 |
| **5. 인과 논리 타당성 (Causal Plausibility)** | JTBD 프레이밍과 메커니즘 경로 간 논리적 비약이나 마법적 사고가 없는가? | **30%** | **LLM** (JSON 구조화) | `jtbd_reframe`, `mechanism_path`, `implicit_assumptions` | LLM 프롬프트가 반환한 `logical_score` (0~30점) $\ge$ 20점 |

### 2. 통과 임계값 및 등급

- **총점**: 100점 만점
- **필수 게이트 조건**: **1. 구조적 완전성**은 무조건 통과해야 함 (Fail 시 총점에 관계없이 즉시 보강).
- **등급 산정**:
  - **통과 (Ready)**: 총점 $\ge$ 85점 AND 구조적 완전성 통과 $\rightarrow$ 루프 종료
  - **보강 필요 (Needs Refinement)**: 60점 $\le$ 총점 < 85점 OR 구조적 완전성 미달 $\rightarrow$ 피드백과 함께 `sharpener` 재호출
  - **재설계 (Back to Drawing Board)**: 총점 < 60점 $\rightarrow$ 부분 보강으로 불가능. `expander` 단계부터 재시작하거나 루프 종료 후 사용자 개입 요청.

### 3. 루프 연동: 피드백 신호 형식

미달된 차원에 대해 `sharpener`의 시스템 프롬프트(또는 User Message)에 컨텍스트로 주입할 구조화된 피드백 템플릿입니다.

```json
{
  "refinement_directive": "가설 품질 스코어카드 검증 결과, 다음 영역의 보완이 필요합니다.",
  "failed_dimensions": [
    {
      "dimension": "리스크 인지 (Risk Awareness)",
      "current_status": "predicted_tradeoff_metrics 배열이 비어있음.",
      "action_required": "이 개입이 성공하더라도 훼손될 수 있는 트레이드오프 지표(예: 체류시간 증가로 인한 이탈률 상승 등)를 최소 1개 이상 도출하여 배열에 포함하시오."
    },
    {
      "dimension": "인과 논리 타당성 (Causal Plausibility)",
      "current_status": "LLM Critique: 개입(버튼 색상 변경)이 행동(결제 전환율 20% 증가)으로 이어지는 메커니즘에 논리적 비약이 큼.",
      "action_required": "mechanism_path를 더 잘게 쪼개어, 사용자의 인지적 변화나 중간 행동 지표(마이크로 전환)를 명시하시오."
    }
  ],
  "constraints": "기존에 잘 작성된 jtbd_reframe은 유지하되, 지적된 필드만 집중적으로 수정하시오."
}
```

### 4. 무한 루프 방지 정책 (Anti-Stagnation)

단순 최대 턴 제한뿐만 아니라, **'개선 없는 헛바퀴'**를 감지하는 정체 방지(Stagnation Detection) 정책을 포함합니다.

1. **최대 턴 제한 (Hard Limit)**: 최대 **3회** (최초 생성 1회 + 재시도 2회). 3회 도달 시, 현재까지의 최선의 결과(`best_score` 기준)를 반환하고 경고 메시지와 함께 루프 강제 종료.
2. **점수 정체 감지 (Delta Check)**: $Turn_{N}$ 의 총점이 $Turn_{N-1}$ 대비 **$\le$ 5점** 상승이거나 오히려 하락한 경우, 다음 턴으로 가지 않고 즉시 루프 종료. (LLM이 피드백을 수용하지 못하고 빙빙 도는 상태로 간주).
3. **동일 차원 반복 실패 (Repeated Failure)**: 2회 연속으로 **동일한 Rule-based 차원**(예: 구조적 완전성)에서 실패할 경우, LLM에게 피드백을 줘도 스키마를 못 맞추는 상태이므로 즉시 루프 중단 후 사용자에게 Fallback.
