# ab-lens 가설품질 스코어카드 (Hypothesis Quality Scorecard, HQS)

## 설계 관점 — 왜 이렇게 짰는가

이 설계의 핵심 차별점 세 가지를 먼저 밝힌다.

1. **"채점"과 "게이트"를 분리한다.** 점수 70이 통과가 아니다. **결격(disqualifier) 차원**이 하나라도 깨지면 총점과 무관하게 미달이다. 가설 품질은 평균이 아니라 **최소 보장**의 문제다 — 측정 불가능한 가설은 다른 차원이 아무리 좋아도 실험으로 못 간다.

2. **LLM 채점은 "값 생성"이 아니라 "이진 판정"으로만 쓴다.** 재현성이 낮은 건 LLM이 0~100 점수를 줄 때다. "이 메커니즘이 인과적으로 그럴듯한가? Y/N + 한 줄 이유"는 훨씬 안정적이다. 그래서 LLM 차원은 전부 **rubric 기반 Y/N/부분(2/1/0)** 으로 강제한다.

3. **정체(stall) 감지를 점수 변화가 아니라 "피드백 소진"으로 본다.** 같은 피드백을 두 번 줬는데 같은 차원이 또 미달이면, 그건 모델이 못 고치는 것이므로 즉시 종료한다 (점수 진동을 기다리지 않음).

---

## 차원 표

7개 차원, 가중 100점. **★ 표시는 결격(disqualifier) 차원** — 미달 시 총점 무관 게이트 차단.

| # | 차원 | 정의 | 가중치 | 판정방식 | HypothesisOutput 매핑 | 통과조건 |
|---|------|------|:---:|:---:|------|------|
| D1 ★ | **측정가능성** (Measurability) | 가설이 명시 지표로 관측·검정 가능한가 | 20 | **룰** | `measurability_confirmed`, `suggested_primary_metric` | `measurability_confirmed==True` **AND** `suggested_primary_metric` 비어있지 않고 실제 지표명(후술 룰) |
| D2 ★ | **반증가능성** (Falsifiability) | 틀릴 수 있는 방향성 주장인가 (동어반복/항진명제 배제) | 15 | **룰+LLM보조** | `sharpened_hypothesis`, `predicted_tradeoff_metrics[]` | 방향어휘 존재(룰) **AND** LLM Y(반증 시나리오 1개 생성 가능) |
| D3 | **메커니즘 구체성** (Mechanism) | 개입→행동→지표 사슬이 빈칸 없이 인과적으로 이어지는가 | 20 | **룰(구조)+LLM(타당성)** | `mechanism_path` | 3-segment 구조 충족(룰) ×2점 + LLM 인과타당성 Y/부분/N → 합산 |
| D4 | **구체성·범위** (Specificity) | 대상·개입·기대효과가 모호어 없이 좁혀졌나 | 15 | **룰** | `sharpened_hypothesis`, `jtbd_reframe` | 모호어 밀도 임계 이하 **AND** 대상 세그먼트/개입 명사 존재 |
| D5 | **가정 노출** (Assumption surfacing) | 숨은 전제를 충분히 드러냈나 | 10 | **룰** | `implicit_assumptions[]` | `len ≥ 2` (Quick) / `≥ 3` (Deep) |
| D6 | **교란 인지** (Confound awareness) | 인과 해석을 위협하는 교란을 식별했나 | 10 | **룰** | `confounder_candidates[]`, `causal_alternative` | `len(confounder_candidates) ≥ 2` **OR** `causal_alternative` 非공란 |
| D7 | **트레이드오프 예측** (Tradeoff) | 좋아지는 지표의 반대급부를 예측했나 | 10 | **룰** | `predicted_tradeoff_metrics[]` | `len ≥ 1` (가드레일 후보 존재) |

### 판정 룰 상세 (결정론 부분)

```python
# D1 측정가능성 (★)
def score_measurability(h) -> int:
    if not h.measurability_confirmed: return 0          # 결격
    m = (h.suggested_primary_metric or "").strip()
    if not m or len(m) < 2: return 0                     # 결격
    # 동어반복 지표 차단: "성공률"처럼 가설어휘 그대로 복붙 금지
    vague = {"성공", "개선", "향상", "효과", "지표", "metric"}
    if m in vague: return 10                             # 약함(부분점)
    return 20

# D3 메커니즘 구조 (룰 부분, 0~10)
def score_mechanism_structure(h) -> int:
    p = h.mechanism_path or ""
    segs = [s for s in re.split(r"[→\->]+", p) if s.strip()]
    if len(segs) < 3: return 0       # 개입/행동/지표 3단 미충족
    if any(len(s.strip()) < 2 for s in segs): return 5
    return 10                        # 나머지 10점은 LLM 인과타당성

# D4 구체성: 모호어 밀도
VAGUE = {"등", "관련", "전반", "다양한", "여러", "적절히", "최적화", "개선", "더 나은", "어느 정도"}
def score_specificity(h) -> int:
    text = (h.sharpened_hypothesis or "") + " " + (h.jtbd_reframe or "")
    toks = text.split()
    density = sum(t in VAGUE for t in toks) / max(len(toks), 1)
    has_target = bool(h.jtbd_reframe and len(h.jtbd_reframe) > 10)
    base = 15 if density < 0.04 else (8 if density < 0.08 else 0)
    return base if has_target else max(base - 7, 0)

# D5~D7 길이 기반 (mode = "quick"|"deep")
def score_assumptions(h, mode): 
    need = 3 if mode=="deep" else 2
    return 10 if len(h.implicit_assumptions) >= need else (5 if h.implicit_assumptions else 0)
def score_confound(h):
    return 10 if (len(h.confounder_candidates) >= 2 or h.causal_alternative) else (5 if h.confounder_candidates else 0)
def score_tradeoff(h):
    return 10 if h.predicted_tradeoff_metrics else 0
```

### LLM 채점 부분 (불가피한 주관 — 이진 rubric로 최소화)

LLM은 **점수를 만들지 않는다**. 아래 단일 구조화 호출로 **3개 Y/부분/N 판정 + 1줄 근거**만 받는다. 한 번의 `call_structured`로 묶어 호출 수·변동 최소화.

```python
class LLMJudgment(BaseModel):
    falsifiable: Literal["Y","N"]            # D2: 반증 시나리오 1개 댈 수 있나
    falsify_scenario: str                    # 그 시나리오(없으면 "")
    mechanism_plausible: Literal["Y","P","N"] # D3: 인과 타당성
    mechanism_gap: str                       # 끊긴 고리 지적(통과면 "")

JUDGE_PROMPT = """다음 가설을 채점한다. 점수 금지, 판정만.
1) falsifiable: 이 가설이 '틀렸다'고 판명날 구체적 관측 시나리오가 존재하나? Y/N + 시나리오.
2) mechanism_plausible: 개입→행동→지표 사슬이 인과적으로 그럴듯한가? 끊긴 고리 있으면 P, 비논리면 N.
가설: {sharpened}
메커니즘: {mechanism_path}
"""
# 매핑: D2 LLM = (falsifiable=="Y" ? +기준충족 : 미달)
#       D3 LLM = {"Y":10, "P":5, "N":0}
```

[가정] `call_structured`가 `Literal` enum을 JSON 스키마 enum으로 강제해 자유생성 노이즈를 막는다고 전제. 안 되면 후처리에서 화이트리스트 검증.

---

## 통과 임계값 + 등급

총점 = D1+...+D7 (max 100). **단, 결격 차원(D1·D2)이 0이면 등급은 자동 "재설계".**

| 등급 | 조건 | 루프 동작 |
|------|------|------|
| **PASS (통과)** | 총점 ≥ **78** **AND** D1==20 **AND** D2 통과 **AND** D3 ≥ 12 | 루프 종료 → bias_screener로 |
| **REFINE (보강필요)** | 60 ≤ 총점 < 78 **OR** (총점≥78인데 결격·D3 약함) | sharpener 재호출 (피드백 주입) |
| **REDESIGN (재설계)** | 총점 < 60 **OR** D1==0 **OR** D2 미달 | expander로 되돌림 (후보 재발산) — 단 최대 1회 |

설계 의도: **78은 "평균 통과"가 아니다.** 결격 게이트(D1=20 필수, D2 필수)를 곱한 뒤의 78이므로, 실질적으로 "측정가능·반증가능이 보장된 상태에서 나머지가 고르게 충족"을 의미한다. PASS 안에 D3≥12를 따로 박은 이유: 메커니즘이 비면 사후 해석이 깨지기 때문 (가설품질의 척추).

---

## 루프 연동 — 미달 차원 → sharpen 재주입 피드백 형식

각 미달 차원은 **(차원, 결손코드, 교정지시)** 삼중항으로 변환되어 sharpener 프롬프트에 주입된다. 길이가 아니라 **무엇을 고칠지**를 명령형으로 전달한다.

```python
FEEDBACK_RULES = {
  "D1": "측정 지표가 비었거나 동어반복이다. {primary}를 '관측 가능한 단일 1차 지표'(예: 전환율, D7 잔존율)로 교체하라.",
  "D2": "반증 불가능하다. 이 가설이 '틀렸다'고 판명날 조건을 본문에 한 문장 추가하라(LLM 지적: {falsify_gap}).",
  "D3": "메커니즘 사슬이 끊겼다: {mechanism_gap}. 개입→행동→지표를 빈칸 없이 '→'로 이어 다시 써라.",
  "D4": "모호어({vague_hits})를 제거하고 대상 세그먼트·개입을 구체 명사로 좁혀라.",
  "D5": "숨은 가정이 {n}개뿐이다. 비즈니스/행동/측정 전제를 {need}개 이상으로 노출하라.",
  "D6": "교란 후보가 부족하다. 시간/선택/외부효과 중 최소 2개를 confounder로 명시하라.",
  "D7": "트레이드오프 미예측. 1차 지표가 오를 때 악화될 가드레일 지표 1개를 predicted_tradeoff에 추가하라.",
}

def build_feedback(scorecard) -> str:
    failed = scorecard.failed_dims()            # 통과조건 미달 차원 리스트
    lines = [f"[{d}] {FEEDBACK_RULES[d].format(**ctx[d])}" for d in failed]
    return "다음 결손만 교정하고 통과한 차원은 건드리지 마라:\n" + "\n".join(lines)
```

핵심: **"통과한 차원은 건드리지 마라"** 지시로 sharpener가 매 턴 전체를 흔들어 점수가 진동하는 것을 방지 (단조 수렴 유도).

---

## 무한루프 방지 정책

3중 차단 — 어느 하나라도 걸리면 종료.

```python
MAX_TURNS = {"quick": 2, "deep": 3}   # mode별 상한 [가정: Deep은 2라운드 sharpener라 +1 여유]

def should_stop(history) -> tuple[bool, str]:
    cur = history[-1]
    # 1) 통과
    if cur.grade == "PASS":               return True, "pass"
    # 2) 최대 턴
    if len(history) >= MAX_TURNS[mode]:    return True, "max_turns(best-so-far 반환)"
    # 3) 정체 감지 = '피드백 소진': 같은 미달 차원 집합이 2회 연속
    if len(history) >= 2 and history[-1].failed_set == history[-2].failed_set:
        return True, "stall(동일 결손 반복 → 모델 한계, best 반환)"
    # 4) 점수 역행 가드: 총점이 직전보다 떨어지면 직전 best 채택 후 1턴만 더
    if cur.total < history[-2].total:      cur = history[-2]  # rollback, 진동 흡수
    return False, "continue"
```

**정체 판정을 점수 수렴(예: Δ<3)이 아니라 "동일 미달 차원 집합 반복"으로 본 이유:** 점수는 LLM 노이즈로 ±5 흔들리지만, *어느 차원이 못 고쳐지는가*는 안정적 신호다. 같은 곳에서 두 번 막히면 모델이 못 푸는 것이므로 턴을 더 줘도 낭비다.

종료 시 항상 **best-so-far**(총점 최고 턴) 반환 — 마지막 턴이 역행했을 수 있으므로 history에서 argmax(total)를 채택.

---

## 호출 비용 요약 (재현성·비용 관점)

| 구성 | LLM 호출/턴 | 비고 |
|------|:---:|------|
| 룰 채점 (D1,D4~D7 전부 + D3 구조) | **0** | 순수 파이썬, 완전 결정론 |
| LLM 판정 (D2 반증 + D3 타당성) | **1** | 묶음 `call_structured`, enum 강제 |

턴당 LLM 1회 × 최대 3턴 = **최악 3회**. 점수 산출은 결정론, LLM은 이진 판정에만 사용 → 재현성 확보.

---

[가정 정리]
- `mode`("quick"/"deep")는 sharpener 라운드 수에서 이미 결정돼 스코어카드에 전달된다고 전제.
- D5의 가정 개수 임계(2/3)는 Quick/Deep 발산 깊이 차이를 반영한 휴리스틱.
- REDESIGN→expander 되돌림은 비용상 **세션당 1회**로 제한(미명시 시 무한 발산 위험).
- LLM enum 강제가 불가하면 화이트리스트 후처리로 동일 효과 보장.
