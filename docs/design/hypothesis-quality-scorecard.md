# ab-lens 가설품질 스코어카드 (Hypothesis Quality Scorecard, HQS v1)

> 본 문서는 3개 독립 설계안(Claude Opus / GPT-5.1-codex / Gemini 3 Pro) + R1 교차비평 + R2 수렴권고를
> 종합한 **단일 최종 설계**다. 부분 짜깁기가 아니라 수렴된 결정을 골격으로 처음부터 일관되게 재작성했다.
> 토론에서 합의되지 않은 절대 임계값은 **캘리브레이션 전까지 봉인**한다(§4, §8).

---

## 1. 설계 원칙 요약

1. **채점과 게이트를 분리한다.** 가설 품질은 평균이 아니라 **최소 보장**의 문제다. 측정 불가·반증 불가 가설은 다른 차원이 아무리 높아도 실험으로 못 간다 → **결격(disqualifier) 게이트**가 총점보다 우선한다.
2. **LLM은 점수를 만들지 않는다.** 연속점수는 호출마다 ±5~8 흔들려 게이트 위에서 동전던지기가 된다. LLM은 오직 **Y/P/N 이진(범주형) 판정 + 1줄 근거**만 내고, 점수는 결정론 파이썬 룰이 매핑한다.
3. **정체는 점수 변화(Δ)가 아니라 "피드백 소진"으로 감지한다.** 같은 차원이 두 번 연속 미달이면 모델이 못 고치는 것이므로 즉시 종료한다. 점수 Δ는 LLM 노이즈에 취약해 폐기.
4. **정체·재설계 시 Expander 롤백하지 않는다.** 컨텍스트 비대화·사용자 원의도 훼손 위험. 대신 **Best-so-far Soft Pass + Caveat**로 전진해 사용자가 판단하게 한다.
5. **길이/개수 휴리스틱은 동어반복 차단 룰과만 결합한다.** 글자 수·리스트 개수 단독 판정은 LLM이 의미 없는 수식어로 우회(gaming)한다.

---

## 2. 차원 표 (6차원, 가중 100점)

`★` = 결격(disqualifier) 게이트 차원 — 미달 시 총점 무관 차단.

| # | 차원 | 정의 | 가중치 | 룰/LLM(Y/P/N) | HypothesisOutput 매핑 | 통과조건 |
|---|------|------|:---:|:---:|------|------|
| **D1 ★** | 측정가능성 (Measurability) | 가설이 명시 1차 지표로 관측·검정 가능한가 | 20 | **룰** | `measurability_confirmed`, `suggested_primary_metric` | `measurability_confirmed==True` **AND** `primary_metric`이 동어반복 화이트리스트(성공/개선/향상/효과/지표) 밖의 실제 지표명 → 게이트 통과(=20) |
| **D2 ★** | 반증가능성 (Falsifiability) | "틀렸다"고 판명날 조건이 존재하는 방향성 주장인가 | 15 | **룰 + LLM(Y/N)** | `sharpened_hypothesis`, `causal_alternative` | 방향어휘 존재(룰) **AND** LLM이 반증 시나리오 1개 생성(Y) → 게이트 통과(=15) |
| **D3** | 인과 메커니즘 (Mechanism) | 개입→행동→지표 사슬이 구조적·인과적으로 이어지는가 | 25 | **룰(0~10) + LLM(Y/P/N→15/8/0)** | `mechanism_path` | 구조 점수 + 타당성 점수 합산. 게이트 아님. 단 PASS엔 ≥15 요구(§4) |
| **D4** | 측정정렬·리스크 (Alignment & Risk) | 보조지표·트레이드오프·교란을 식별했는가 | 20 | **룰** | `suggested_secondary_metrics`, `predicted_tradeoff_metrics`, `confounder_candidates` | 하위 가산(§3). tradeoff·confound 독립 채점 |
| **D5** | 대안탐색 (Alternative) | 다른 후보·인과 대안을 검토했는가 | 10 | **룰** | `rejected_alternatives`, `causal_alternative` | `len(rejected)≥2`→10 / `1 OR causal_alternative`→5 / else 0 |
| **D6** | 가설명료성 (Clarity) | 문장이 모호어 없이 구체적·검증가능한가 | 10 | **LLM(Y/P/N) + 모호어 차단(룰)** | `sharpened_hypothesis` | 모호어 밀도 임계 이하(룰 게이밍 차단) **AND** LLM 명료성 Y/P/N |

**설계 메모 (토론 반영):**
- D2를 독립 차원으로 승격한 건 B의 Popper 프레이밍 채택. "언제 틀렸다고 할 것인가"는 실험 설계의 척추.
- D4는 C의 "리스크 인지" 묶음을 받되, R1에서 지적된 **AND 묶음의 피드백 해상도 저하** 문제를 피하려 tradeoff/confound를 **독립 가산**으로 분리(B 권고). 하나가 빠져도 차원 전체가 죽지 않는다.
- D3 메커니즘은 구조(룰)와 의미(LLM)를 **명시적으로 합산**해 R1 미해결쟁점(합산 로직 불명확)을 해소. LLM이 N이어도 구조 점수는 살린다.

---

## 3. 게이트 차원 상세 (결정론 룰 + LLM Y/N 판정)

### 결정론 룰 (점수 산출 — 완전 재현)

```python
import re

# 동어반복 화이트리스트 (지표가 가설 어휘를 그대로 복붙한 경우 차단)
VAGUE_METRIC = {"성공", "개선", "향상", "효과", "지표", "metric"}
# 구체성 모호어 (D6 게이밍 차단)
VAGUE_D6 = {"등", "관련", "전반", "다양한", "여러", "적절히", "최적화", "더 나은", "어느 정도"}
# 방향어휘 (D2 룰 파트 — 반증 가능한 방향성 주장인지)
DIRECTION_RX = re.compile(r"(증가|감소|상승|하락|높|낮|늘|줄|개선되|악화|차이)")


# ── D1 측정가능성 (★ 게이트, max 20) ─────────────────────
def d1_measurability(h) -> int:
    if not h.measurability_confirmed:
        return 0                                  # 결격
    m = (h.suggested_primary_metric or "").strip()
    if not m or len(m) < 2:
        return 0                                  # 결격: 지표 없음
    if m in VAGUE_METRIC:
        return 10                                 # 동어반복 → 부분점 (게이트 미통과)
    return 20                                      # 실제 지표명 → 게이트 통과


# ── D2 반증가능성 (★ 게이트, max 15) = 룰(방향) AND LLM(falsifiable==Y) ─
def d2_falsifiability(h, llm) -> int:
    has_direction = bool(DIRECTION_RX.search(h.sharpened_hypothesis or ""))
    if has_direction and llm.falsifiable == "Y":
        return 15                                 # 게이트 통과
    return 0                                       # 결격


def gate_passed(d1_score: int, d2_score: int) -> bool:
    """결격 게이트: D1·D2가 만점(게이트 통과)이어야 PASS/CAVEAT 진입 가능."""
    return d1_score == 20 and d2_score == 15
```

### 게이트 판정 규칙 정리

| 게이트 | 룰 파트 (결정론) | LLM 파트 (Y/N) | 통과 조건 |
|------|------|------|------|
| **D1 측정가능성** | `measurability_confirmed==True` AND 지표명이 동어반복 화이트리스트 밖 | 없음 (순수 룰) | 둘 다 충족 → 20점, 동어반복이면 10점(미통과), 지표 없으면 0점 |
| **D2 반증가능성** | `sharpened_hypothesis`에 방향어휘 존재 | "이 가설이 틀렸다고 판명날 관측 시나리오가 있는가?" → Y/N | 룰 AND LLM=Y → 15점, 하나라도 실패 → 0점 |

> D1을 순수 룰로 둔 이유: 측정가능성은 `measurability_confirmed` 플래그 + 지표명 실재성으로 결정론 판정이 가능하다. LLM을 끼우면 게이트가 노이즈 위에 선다.
> D2에 LLM을 넣은 이유: "방향어휘 존재"만으론 동어반복("성공률이 증가한다")을 못 거른다. **반증 시나리오 생성 가능성**은 의미 판단이라 LLM Y/N이 불가피하되, 게이트가 흔들리지 않도록 **룰(방향) AND LLM(Y)** 두 조건을 모두 요구한다.

---

## 4. 등급 체계 (PASS / ACCEPTABLE w/ Caveat / REDESIGN)

**절대 임계 봉인 명시:** A의 78·C의 85·B의 70 모두 캘리브레이션 데이터 없는 매직넘버다(R1 3자 동의). v1은 **결격 게이트 + 상대등급(2단계)**으로 출발한다. 아래 총점 임계(80/68)는 **잠정값**이며 게이트가 실질 품질을 보장한다. 운영 로그로 ROC를 잡아 재조정한다(§8).

| 등급 | 조건 | 루프 동작 |
|------|------|------|
| **PASS** (통과) | 게이트 통과(D1==20 AND D2==15) **AND** D3≥15 **AND** 총점 ≥ **80**(잠정) | 루프 종료 → bias_screener로 전진 |
| **ACCEPTABLE w/ Caveat** (조건부 통과) | 게이트 통과(D1==20 AND D2==15) **AND** 총점 ≥ **68**(잠정), 단 D3<15 또는 일부 차원 약함 | **통과**하되 약점 차원을 Caveat로 bias_screener·UI에 전달 |
| **REFINE** (보강 필요) | 게이트 통과했으나 총점 < 68 | sharpener 재호출 (§5 피드백 주입) |
| **REDESIGN** (재설계) | 게이트 결격(D1<20 OR D2<15) | §6 정체 정책에 따라 sharpener 강제 피드백 → 안 되면 Soft Pass. **Expander 롤백 안 함** |

**핵심 설계 결정:**
- **상대등급 우선, 절대임계 봉인.** 등급의 1차 결정 요인은 **게이트 통과 여부**다. 게이트를 곱한 뒤의 총점 임계는 보조이며 캘리브레이션 전까지 신뢰하지 않는다.
- **ACCEPTABLE에 게이트 통과 필수 조건.** B의 "70점 Acceptable"을 채택하되, **측정·반증 게이트 통과 없이는 진입 불가**로 못박아 "측정 불가인데 통과" 모순을 차단(B 자기수정 + A·C 동의).
- **REDESIGN ≠ Expander 롤백.** R1/R2 만장일치. 게이트 결격이라도 sharpener에 "결격 차원만 고쳐라" 강제 피드백으로 처리하고, 정체하면 Best-so-far Soft Pass로 전진한다.

### 점수 매핑 코드 (결정론 룰 + LLM 이진)

```python
# ── D3 메커니즘 (max 25) = 구조(룰 0~10) + 타당성(LLM Y/P/N → 15/8/0) ──
def d3_mechanism(h, llm) -> int:
    segs = [s for s in re.split(r"[→\->]+", h.mechanism_path or "") if s.strip()]
    if len(segs) < 3:
        struct = 0                                # 개입/행동/지표 3단 미충족
    elif any(len(s.strip()) < 2 for s in segs):
        struct = 5                                # 빈 세그먼트
    else:
        struct = 10
    plaus = {"Y": 15, "P": 8, "N": 0}[llm.mechanism_plausible]
    return struct + plaus                          # N이어도 struct는 살림


# ── D4 측정정렬·리스크 (max 20) — tradeoff/confound 독립 가산 ──
def d4_alignment_risk(h) -> int:
    s = 7 if h.measurability_confirmed else 0
    s += 5 if len(h.suggested_secondary_metrics) >= 1 else 0
    s += 4 if len(h.predicted_tradeoff_metrics) >= 1 else 0          # 부작용 예측
    s += {0: 0, 1: 2}.get(len(h.confounder_candidates), 4)          # ≥2→4, 1→2, 0→0
    return min(s, 20)


# ── D5 대안탐색 (max 10) ──
def d5_alternative(h) -> int:
    n = len(h.rejected_alternatives)
    if n >= 2:
        return 10
    if n == 1 or h.causal_alternative:
        return 5
    return 0


# ── D6 명료성 (max 10) = 모호어 게이밍 차단(룰) × LLM 판정 ──
def d6_clarity(h, llm) -> int:
    toks = (h.sharpened_hypothesis or "").split()
    density = sum(t in VAGUE_D6 for t in toks) / max(len(toks), 1)
    if density >= 0.08:
        return 0                                   # 모호어 과다 → 게이밍 차단
    return {"Y": 10, "P": 5, "N": 0}[llm.clarity]


# ── 총점 + 등급 ──
def score_hypothesis(h, llm) -> dict:
    s = {
        "D1": d1_measurability(h),
        "D2": d2_falsifiability(h, llm),
        "D3": d3_mechanism(h, llm),
        "D4": d4_alignment_risk(h),
        "D5": d5_alternative(h),
        "D6": d6_clarity(h, llm),
    }
    total = sum(s.values())
    gate = gate_passed(s["D1"], s["D2"])
    failed = [d for d in s if _below_pass_threshold(d, s[d])]   # §5 통과조건 기준

    if not gate:
        grade = "REDESIGN"
    elif s["D3"] >= 15 and total >= 80:            # 잠정 임계
        grade = "PASS"
    elif total >= 68:                              # 잠정 임계
        grade = "ACCEPTABLE_CAVEAT"
    else:
        grade = "REFINE"

    return {"scores": s, "total": total, "gate": gate,
            "grade": grade, "failed_set": frozenset(failed)}
```

### LLM 판정 — 턴당 단 1회 (재현성·비용)

```python
from typing import Literal
from pydantic import BaseModel

class LLMJudgment(BaseModel):
    falsifiable: Literal["Y", "N"]               # D2: 반증 시나리오 도출 가능?
    falsify_scenario: str                        # 그 시나리오 (없으면 "")
    mechanism_plausible: Literal["Y", "P", "N"]  # D3: 인과 타당성
    mechanism_gap: str                           # 끊긴 고리 (통과면 "")
    clarity: Literal["Y", "P", "N"]              # D6: 명료성

JUDGE_PROMPT = """다음 가설을 채점한다. 점수(숫자) 생성 금지, 판정만.

1) falsifiable: 이 가설이 '틀렸다'고 판명날 구체적 관측 시나리오가 존재하나?
   Y → falsify_scenario에 1문장 작성 / N → scenario는 ""
2) mechanism_plausible: 개입→행동→지표 사슬이 인과적으로 그럴듯한가?
   Y(타당) / P(중간 비약 있음 → mechanism_gap에 지적) / N(비논리 → 이유)
3) clarity: 문장이 주어-동사-목적어 명확하고 검증 가능한가? Y / P / N

가설: {sharpened_hypothesis}
메커니즘: {mechanism_path}
JTBD: {jtbd_reframe}
"""
```

> **멀티프로바이더 Enum 강제 (C의 미해결쟁점):** Anthropic / OpenRouter / Gemini는 structured output 강제력이 제각각이다. `Literal` enum이 JSON 스키마 enum으로 강제되지 않는 provider를 대비해 **화이트리스트 정규식 폴백** 필수. Enum 밖 값이 오면 가장 보수적 등급(`N`)으로 처리한다.

---

## 5. 루프 연동: 미달 차원 → sharpener 재호출 피드백 형식

미달 차원을 `(dimension, current_status, action_required)` JSON 배열로 변환해 sharpener에 주입한다(C 구조). **"통과한 차원은 건드리지 마라"** 메타 지시로 단조 수렴을 유도한다(A·C 공통).

### 피드백 JSON 템플릿

```json
{
  "refinement_directive": "가설 품질 스코어카드 검증 결과, 아래 결손만 교정하고 통과한 차원은 절대 수정하지 마시오.",
  "failed_dimensions": [
    {
      "dimension": "D3 인과 메커니즘",
      "current_status": "LLM 판정 P: 개입(버튼 색상 변경)→전환 사이 인지/행동 변화가 누락됨.",
      "action_required": "mechanism_path를 더 잘게 쪼개 마이크로 전환(클릭률·체류시간) 같은 중간 노드를 '개입 → 인지변화 → 중간행동 → 지표'로 명시하시오."
    },
    {
      "dimension": "D4 측정정렬·리스크",
      "current_status": "predicted_tradeoff_metrics 배열이 비어 있음.",
      "action_required": "1차 지표가 오를 때 악화될 수 있는 가드레일 지표 1개 이상을 predicted_tradeoff_metrics에 추가하시오."
    }
  ],
  "constraints": "잘 작성된 jtbd_reframe과 이미 통과한 차원은 그대로 유지하시오."
}
```

### 차원별 action_required 룰

| 미달 차원 | current_status 트리거 | action_required |
|------|------|------|
| **D1** | primary_metric 비었거나 동어반복 | "1차 지표 '{metric}'이 동어반복이다. '전환율', 'D7 잔존율' 같은 관측 가능한 단일 지표로 교체하시오." |
| **D2** | 방향어휘 없음 OR LLM falsifiable=N | "반증 조건이 없다. '지표 X가 Y% 미만이면 가설 기각' 같은 실패 조건을 sharpened_hypothesis에 1문장 추가하시오. (LLM 지적: {falsify_gap})" |
| **D3 구조** | 화살표<2 또는 빈 세그먼트 | "mechanism_path가 불완전하다. '개입 → 행동변화 → 관측지표'를 빈칸 없이 '→'로 이어 재작성하시오." |
| **D3 타당성** | LLM mechanism_plausible=P/N | "인과 경로에 비약: {mechanism_gap}. 끊긴 중간 단계를 명시하시오." |
| **D4 tradeoff** | tradeoff 0개 | "트레이드오프 미예측. 1차 지표 상승 시 악화될 가드레일 지표 1개를 predicted_tradeoff_metrics에 추가하시오." |
| **D4 confound** | confounder<2개 | "교란 후보가 부족하다. 시간/선택/외부효과 중 최소 2개를 confounder_candidates에 명시하시오." |
| **D5** | rejected<2 AND causal_alt 없음 | "대안 검토 근거가 없다. rejected_alternatives에 '왜 다른 후보보다 이 가설이 나은지' 1개 이상 추가하시오." |
| **D6** | 모호어 밀도 과다 OR LLM clarity=P/N | "문장이 모호하다. sharpened_hypothesis를 주어-동사-목적어가 명확한 한 문장으로 재작성하고 예상 효과 방향을 포함하시오." |

```python
def build_feedback(scorecard) -> dict:
    items = []
    for d in sorted(scorecard["failed_set"]):
        items.append({
            "dimension": DIM_LABEL[d],
            "current_status": render_status(d, scorecard, ctx),
            "action_required": ACTION_RULES[d].format(**ctx[d]),
        })
    return {
        "refinement_directive": "아래 결손만 교정하고 통과한 차원은 절대 수정하지 마시오.",
        "failed_dimensions": items,
        "constraints": "잘 작성된 jtbd_reframe과 이미 통과한 차원은 그대로 유지하시오.",
    }
```

---

## 6. 정체 방지 정책 (Best-so-far Soft Pass)

**정체 = 피드백 소진 = 동일 미달 차원 집합 2회 연속.** 점수 Δ가 아니라 "어느 차원이 못 고쳐지는가"를 신호로 쓴다(점수는 LLM 노이즈로 ±5 흔들려도 미달 차원 집합은 안정적). 3중 차단, 어느 하나라도 걸리면 종료하며 **항상 best-so-far(argmax 총점) 반환**.

```python
MAX_TURNS = {"quick": 2, "deep": 3}   # 최초 1회 + refine N회

def should_stop(history, mode) -> tuple[bool, str, object]:
    cur = history[-1]
    best = max(history, key=lambda x: x["total"])

    # 1) 통과
    if cur["grade"] in ("PASS", "ACCEPTABLE_CAVEAT"):
        return True, "pass", cur

    # 2) 최대 턴 → Best-so-far Soft Pass
    if len(history) >= MAX_TURNS[mode]:
        return True, "max_turns → best-so-far soft pass + caveat", best

    # 3) 주신호: 동일 미달 차원 집합 2회 연속 (룰+LLM 포함)
    if len(history) >= 2 and cur["failed_set"] == history[-2]["failed_set"]:
        return True, "stall(동일 결손 반복) → best-so-far soft pass + caveat", best

    # 4) 보조신호: 동일 '룰' 차원만 2회 반복 (LLM 변동 배제 안전망)
    if (len(history) >= 2
            and cur["failed_rule_dims"]
            and cur["failed_rule_dims"] == history[-2]["failed_rule_dims"]):
        return True, "stall(rule only) → best-so-far soft pass + caveat", best

    return False, "continue", None
```

**정책 핵심:**
- **주신호 = 동일 미달 차원 집합 반복**(A). 점수 Δ≤5(B·C 원안)는 노이즈로 폐기.
- **보조신호 = 동일 룰 차원만 반복**(C). LLM 판정이 흔들릴 때를 위한 순수 결정론 안전망. 주신호와 **OR가 아니라 위계** — 주신호 우선, 룰 신호는 보강.
- **Expander 롤백 전면 미채택**(R1·R2 만장일치). 정체·재설계 모두 **전진(Soft Pass)**. 게이트 결격으로 정체해도 best-so-far에 "측정/반증 미보장" Caveat를 달아 bias_screener·사용자에게 넘기고, 사용자가 재설계 여부를 판단하게 한다. 자동 Expander 발산은 (1)컨텍스트 비대화 (2)원의도 훼손 (3)비용 3중 리스크.
- **최대 턴:** Quick 2 / Deep 3 (Deep은 2라운드 sharpener라 +1 여유).

### 비용·재현성 요약

| 구성 | LLM 호출/턴 |
|------|:---:|
| 룰 채점 (D1, D4, D5 + D3 구조 + D6 모호어) | 0 |
| LLM 이진 판정 (D2·D3·D6 묶음 1콜) | 1 |

턴당 1콜 × 최대 3턴 = **최악 3콜**. 점수는 결정론, LLM은 이진 판정에만.

---

## 7. 채택 출처 표기

| 채택 결정 | 출처 | 비고 |
|------|------|------|
| 결격(disqualifier) 게이트 — 측정·반증 총점 무관 차단 | **A** (D1·D2) + **C**(구조적 완전성 게이트) 독립 수렴 | 가설품질=최소보장 철학 |
| LLM 연속점수 금지, Y/P/N 이진 판정 강제 | **A** | C의 0~30·B의 5점 폐기. 재현성 핵심 |
| 반증가능성을 독립 차원으로 승격 | **B** (D3) | Popper 프레이밍 |
| 메커니즘 = 구조(룰) + 타당성(LLM Y/P/N) 명시 합산 | **A** + R1 합산로직 해소안 | B의 15자·C의 화살표만 폐기 |
| D4 tradeoff/confound 독립 가산 (AND 묶음 회피) | **B** 권고 (C의 D3 묶음 수정) | 피드백 해상도 보존 |
| ACCEPTABLE w/ Caveat 2단계 등급 | **B** | 단 게이트 통과 필수 조건 추가(A·C 동의) |
| 절대 임계 봉인 + 상대등급 우선 | **A·B·C 만장일치** | 매직넘버 캘리브레이션 전 봉인 |
| 정체 감지 = 동일 미달 차원 집합 반복 | **A** (+ C의 룰 차원 반복 보조) | 점수 Δ 폐기 |
| 정체 시 Best-so-far Soft Pass (Expander 롤백 아님) | **C** 강력 주장 + **A·B** 동의 | 컨텍스트·원의도 보호 |
| 피드백 JSON 구조 (`failed_dimensions` 배열) | **C** | A의 dict보다 체계적 |
| "통과 차원 건드리지 마라" 메타 지시 | **A·C** 공통 | 단조 수렴 |
| 멀티프로바이더 Enum 정규식 폴백 | **C** 미해결쟁점 해소 | 보수적 등급(N) 처리 |
| 동어반복/모호어 차단 룰 (길이 휴리스틱과 결합) | **A** | 게이밍 봉쇄 |

---

## 8. v1에서 의도적으로 봉인한 것 (정직성)

1. **절대 임계 80/68은 잠정값.** 실제 가설 20~30개를 3개 모델이 채점·캘리브레이션하기 전엔 정당화 불가. v1 운영 로그로 ROC를 잡아 재조정. 그 전까지 등급의 실질 결정은 **게이트 통과 여부**다.
2. **HypothesisOutput 필드 충족률 미검증.** `confounder_candidates`·`rejected_alternatives` 등이 자주 빈 배열이면 룰 차원이 0점으로 쏠려 REDESIGN이 폭증한다. 상류 sharpener/expander 출력 분포를 먼저 측정해야 한다.
3. **LLM 이진 판정의 경계 재현성.** Y/N 경계 케이스는 같은 가설 2회 채점 일치율(목표 ≥95%)을 측정해 검증 필요.
4. **모델 전환 옵션 미채택.** "Claude가 못 고친 D3을 GPT에 넘기기"(B 제안)는 멀티모델 분업과 엮이는 별도 과제로 분리.

---

## 9. 구현 위치 (참고)

```
src/hypothesis/
  quality_scorecard.py      # 6차원 채점 로직 (d1~d6, score_hypothesis, should_stop)
  scorecard_schemas.py      # Pydantic: LLMJudgment, ScorecardResult
  feedback_generator.py     # build_feedback + ACTION_RULES 템플릿
```

핵심 진입점: `score_hypothesis(h: HypothesisOutput, llm: LLMJudgment) -> dict`,
`should_stop(history, mode)`, `build_feedback(scorecard) -> dict`.
