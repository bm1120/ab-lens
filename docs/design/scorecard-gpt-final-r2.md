# 통합 스코어카드 최종 권고안

## 핵심 설계 결정 (쟁점 해결)

### ① LLM 채점 척도
**결론: Y/P/N 이진 판정만, 연속점수 금지**
- LLM은 `Literal["Y","P","N"]` enum 강제 구조화 출력
- 점수 매핑은 파이썬 룰 (`{"Y":10, "P":5, "N":0}`)
- 재현성 확보 (B의 5점, C의 30점 척도는 폐기)

### ② 통과 임계값 + 등급
**결론: 2단계 적응적 통과 (B안 기반)**

| 등급 | 조건 | 액션 |
|-----|------|------|
| **READY** | 총점 ≥85 AND 결격 0개 | 즉시 통과 |
| **ACCEPTABLE** | 70≤총점<85 AND 결격 0개 | 통과 + 미달 차원 caveat 경고 |
| **REFINE** | 총점 50~69 OR 결격 1개 | sharpener 재호출 (최대 2회) |
| **REDESIGN** | 총점<50 OR 결격 2개 OR 구조결함* | expander 재실행 권고 (1회만) |

*구조결함 = D1<16 OR D3<10

### ③ 정체 시 액션
**결론: Best-so-far 반환 (A안)**
- 동일 미달 차원 집합 2회 반복 → 즉시 종료
- expander 롤백은 위험 (컨텍스트 폭발, 사용자 의도 훼손)
- 최고 총점 턴 반환 + 미해결 피드백 첨부

### ④ 길이/개수 휴리스틱
**결론: 최소화 + 동어반복 차단**
- 필드 존재 여부만 체크 (길이 X)
- 개수 임계 불가피 시 의미 검증 병행 (vague 키워드 필터)
- B의 "15자 이상" 폐기

---

## 차원 표 (6개 차원, 100점)

| 차원 | 정의 | 가중치 | 판정 | 매핑 필드 | 통과조건 |
|-----|------|--------|------|---------|---------|
| **D1 ★측정가능성** | 1차 지표가 관측 가능한가 | 20 | 룰 | `measurability_confirmed`, `suggested_primary_metric` | `confirmed==True` AND `primary_metric` 非공란 AND 비동어반복* |
| **D2 ★반증가능성** | "틀렸다" 판명 조건 존재하는가 | 15 | 룰+LLM | `causal_alternative`, `sharpened_hypothesis` | `causal_alternative` 존재 OR LLM(반증시나리오) == "Y" |
| **D3 메커니즘 구체성** | 개입→행동→지표 사슬이 구조+인과적으로 타당한가 | 25 | 룰+LLM | `mechanism_path` | 구조(화살표≥2, 각 세그먼트>2자) = 10점 + LLM(타당성 Y/P/N) = 10/5/0 |
| **D4 리스크 인지** | 트레이드오프·교란 변수 식별했나 | 15 | 룰 | `predicted_tradeoff_metrics`, `confounder_candidates` | `tradeoff≥1` = 7점 + `confounders≥2` = 8점 (각 독립) |
| **D5 대안 탐색** | 다른 후보와 비교 근거 있나 | 10 | 룰 | `rejected_alternatives`, `causal_alternative` | `rejected≥1` = 7점 + `causal_alt` 존재 = 3점 |
| **D6 가정 노출** | 숨은 전제 드러났나 | 15 | 룰 | `implicit_assumptions` | `len≥3` = 15점, `2` = 10점, `1` = 5점, `0` = 0점 |

**★ = 결격 차원** (0점 시 총점 무관 REFINE 이상)

*동어반복: `{"성공","개선","향상","효과","전환","지표"}` 등 vague 키워드만 있으면 D1=10점(부분), 구체 지표면 20점

---

## 게이트 차원 (필수 통과)

ACCEPTABLE/READY 등급 진입 조건:
```
D1 ≥ 16점 (동어반복 아닌 지표 존재)
AND
D2 ≥ 8점 (반증조건 최소 1개)
```
위 미충족 시 자동 REFINE (총점 무관)

---

## LLM 판정 프롬프트 (단일 호출)

```python
class HQSJudgment(BaseModel):
    falsifiable: Literal["Y","N"]           # D2: 반증 시나리오 댈 수 있나
    falsify_scenario: str                   # 그 시나리오 (없으면 "")
    mechanism_valid: Literal["Y","P","N"]  # D3: 인과경로 타당성
    mechanism_gap: str                      # 끊긴 고리 (통과면 "")

JUDGE_PROMPT = """
다음 가설을 2가지만 판정하라 (점수 금지).

1) falsifiable: "이 가설이 틀렸다"고 판명날 구체적 관측 시나리오가 존재하는가?
   - Y: 시나리오 1개 댈 수 있음 → falsify_scenario에 작성
   - N: 반증 불가능 → scenario는 ""

2) mechanism_valid: 개입→행동→지표 사슬에 논리적 비약이 없는가?
   - Y: 인과고리 타당
   - P: 중간 단계 비약 있음 (mechanism_gap에 지적)
   - N: 전체 비논리 (mechanism_gap에 이유)

가설: {sharpened_hypothesis}
메커니즘: {mechanism_path}
JTBD: {jtbd_reframe}
"""
```

---

## 루프 연동 — 피드백 생성

```python
FEEDBACK_TEMPLATES = {
    "D1": "1차 지표가 '{metric}'(동어반복)이다. '클릭률', 'D7 잔존율' 같은 관측 가능 지표로 교체하라.",
    "D2": "반증 조건이 없다. '지표 X가 Y% 미만이면 가설 기각' 같은 문장을 hypothesis에 추가하라.",
    "D3_struct": "mechanism_path가 불완전하다 (화살표<2 또는 세그먼트 비어있음). '개입 → 행동변화 → 지표'로 재작성하라.",
    "D3_logic": "인과 경로에 논리적 비약: {gap}. 중간 단계를 명시하라.",
    "D4_tradeoff": "트레이드오프 미예측. 1차 지표 상승 시 악화될 지표 1개를 predicted_tradeoff에 추가하라.",
    "D4_confound": "교란 후보<2개. 시간/선택/외부효과 중 2개 이상을 confounder_candidates에 나열하라.",
    "D5": "대안 탐색 증거 없음. rejected_alternatives에 '왜 다른 후보보다 나은지' 1개 이상 추가하라.",
    "D6": "숨은 가정<3개. 비즈니스/행동/측정 전제를 3개 이상 implicit_assumptions에 노출하라.",
}

def build_feedback(failed_dims: list) -> str:
    lines = [f"[{d.name}] {FEEDBACK_TEMPLATES[d.code].format(**d.ctx)}" 
             for d in failed_dims]
    return f"""
가설 품질 미달 차원만 교정하라. 통과한 차원은 건드리지 마라.

{chr(10).join(lines)}
"""
```

---

## 무한루프 방지 정책

```python
MAX_TURNS = 3  # 최초 1회 + refine 2회

def should_stop(history: list[Scorecard]) -> tuple[bool, str]:
    cur = history[-1]
    
    # 1) 통과
    if cur.grade in ["READY", "ACCEPTABLE"]:
        return True, "pass"
    
    # 2) 최대 턴
    if len(history) >= MAX_TURNS:
        best = max(history, key=lambda x: x.total)
        return True, f"max_turns(best={best.total}점 반환)"
    
    # 3) 정체 = 동일 미달 차원 집합 2회 반복
    if len(history) >= 2:
        if history[-1].failed_set == history[-2].failed_set:
            best = max(history, key=lambda x: x.total)
            return True, f"stall(피드백 소진, best={best.total}점)"
    
    # 4) 구조결함 → expander (1회만)
    if (cur.D1 < 16 or cur.D3 < 10) and not history.expander_retry_done:
        return True, "structural_failure(expander 재실행)"
    
    return False, "continue"
```

---

## 등급별 UI 메시지

```python
GRADE_MESSAGES = {
    "READY": "✅ 실험 준비 완료",
    "ACCEPTABLE": "⚠️ 통과 (다음 영역 보완 권장: {caveats})",
    "REFINE": "🔄 보강 필요 — {failed_dims} 교정 후 재시도 중...",
    "REDESIGN": "❌ 구조적 결함 — 가설을 처음부터 재설계하세요."
}
```

---

## 구현 위치

```
src/hypothesis/
  quality_scorecard.py      # 채점 로직
  scorecard_schemas.py      # Pydantic models (HQSJudgment, ScorecardResult)
  feedback_generator.py     # 피드백 템플릿 + 주입
```

---

## 검증 체크리스트

- [ ] `Literal["Y","P","N"]` enum 강제 (Anthropic/OpenRouter/Gemini 전부)
- [ ] 동어반복 vague 키워드 리스트 확정
- [ ] 실제 가설 20개에 3회 채점 → 재현성 측정 (Y/N 일치율 ≥95%)
- [ ] best-so-far 반환 시 미해결 피드백 첨부 확인
- [ ] ACCEPTABLE 등급 caveat UI 표시 검증
