이미 R1까지 끝난 깊은 토론이다. 세 비평이 거의 같은 결론으로 수렴했으니 통합 권고안만 작성하면 된다. 도구 없이 바로 작성한다.

# ab-lens 통합 가설품질 스코어카드 (HQS v1) — 최종 권고안

## 0. 토론 수렴 요약 (R1 3자 합의)

세 비평이 독립적으로 같은 결론에 도달한 부분 → **확정**:
- LLM은 점수 생성 금지, Y/P/N 이진 판정만
- 게이트(결격)와 스코어 분리
- 정체 감지 = 점수 Δ가 아니라 "동일 미달 차원 반복"
- 정체 시 Best-so-far Soft Pass (Expander 롤백 **아님**)
- 길이/개수 휴리스틱 → 동어반복 차단 룰과 반드시 결합
- 절대 임계값은 매직넘버 → 캘리브레이션 전까지 봉인, 결격+상대등급으로 출발

---

## 1. 차원표 (6차원, 가중 100점)

D1·D2는 **게이트 차원(★)** — 미달 시 총점 무관 차단.

| # | 차원 | 가중치 | 룰/LLM | HypothesisOutput 매핑 | 통과조건 |
|---|------|:---:|:---:|------|------|
| **D1 ★** | 측정가능성 | 20 | **룰** | `measurability_confirmed`, `suggested_primary_metric` | `measurability_confirmed==True` **AND** primary_metric이 동어반복 화이트리스트(성공/개선/향상/효과/지표) 밖의 실제 지표명 |
| **D2 ★** | 반증가능성 | 15 | **룰+LLM(Y/N)** | `sharpened_hypothesis`, `causal_alternative` | 방향어휘 존재(룰) **AND** LLM이 반증 시나리오 1개 생성 가능(Y) |
| **D3** | 메커니즘 (구조+타당성) | 25 | **룰(0~10)+LLM(Y/P/N)** | `mechanism_path` | 합산 점수 — 게이트 아님, 단 PASS엔 ≥15 요구 (§3) |
| **D4** | 측정정렬·리스크 | 20 | **룰** | `measurability_confirmed`, `suggested_secondary_metrics`, `predicted_tradeoff_metrics`, `confounder_candidates` | 하위 가산 (§2) |
| **D5** | 대안탐색 | 10 | **룰** | `rejected_alternatives`, `causal_alternative` | `len(rejected)≥2` →10 / `1 or causal_alternative` →5 / else 0 |
| **D6** | 가설명료성 | 10 | **LLM(Y/P/N)** | `sharpened_hypothesis` | 모호어 밀도(룰) 게이밍 차단 + LLM 명료성 판정 |

**핵심 설계 결정 (R1 쟁점 ④ 길이/개수 휴리스틱):**
B의 "15자 이상"·C의 "화살표만" 전면 폐기. 개수/길이 룰은 **반드시 동어반복 화이트리스트 차단과 결합**. 메커니즘은 구조(룰)와 의미(LLM Y/P/N)를 분리 채점 후 합산하여 "글자 채우기 게이밍" 봉쇄.

---

## 2. 점수 매핑 (결정론 룰 + LLM 이진)

```python
# D1 측정가능성 (★ 게이트, max 20)
def d1(h):
    if not h.measurability_confirmed: return 0          # 결격
    m = (h.suggested_primary_metric or "").strip()
    VAGUE = {"성공","개선","향상","효과","지표","metric"}
    if not m or len(m) < 2: return 0                     # 결격
    if m in VAGUE: return 10                             # 동어반복 → 부분
    return 20

# D2 반증가능성 (★ 게이트, max 15)  룰(방향어휘) AND LLM(falsifiable==Y)
def d2(h, llm):
    has_dir = bool(DIRECTION_RX.search(h.sharpened_hypothesis or ""))  # 증가/감소/높/낮 등
    if not (has_dir and llm.falsifiable == "Y"): return 0  # 결격
    return 15

# D3 메커니즘 (max 25) = 구조(룰 0~10) + 타당성(LLM Y/P/N → 15/8/0)
#   ※ R1 미해결쟁점(합산로직) 해소: 두 부분을 명시적으로 더한다
def d3(h, llm):
    segs = [s for s in re.split(r"[→\-]+", h.mechanism_path or "") if s.strip()]
    struct = 0 if len(segs) < 3 else (5 if any(len(s.strip())<2 for s in segs) else 10)
    plaus = {"Y":15, "P":8, "N":0}[llm.mechanism_plausible]  # N이어도 struct는 살림
    return struct + plaus

# D4 측정정렬·리스크 (max 20) — tradeoff/confounder 세분화 (R1: 0/10 이분법 폐기)
def d4(h):
    s = 7 if h.measurability_confirmed else 0
    s += 5 if len(h.suggested_secondary_metrics) >= 1 else 0
    s += {0:0, 1:4}.get(len(h.predicted_tradeoff_metrics), 4)  # ≥1 →4
    s += {0:0, 1:2}.get(len(h.confounder_candidates), 4)        # ≥2 →4, 1 →2
    return min(s, 20)

# D5 대안탐색 (max 10)
def d5(h):
    n = len(h.rejected_alternatives)
    return 10 if n >= 2 else (5 if (n == 1 or h.causal_alternative) else 0)

# D6 명료성 (max 10) = 모호어 게이밍 차단(룰) × LLM 판정
VAGUE_D6 = {"등","관련","전반","다양한","여러","적절히","최적화","더 나은"}
def d6(h, llm):
    toks = (h.sharpened_hypothesis or "").split()
    density = sum(t in VAGUE_D6 for t in toks)/max(len(toks),1)
    if density >= 0.08: return 0           # 모호어 과다 → 게이밍 차단
    return {"Y":10, "P":5, "N":0}[llm.clarity]
```

**LLM 호출 — 턴당 단 1회** (R1 합의: 재현성·비용):
```python
class LLMJudgment(BaseModel):              # enum 강제 + 정규식 폴백(멀티프로바이더)
    falsifiable: Literal["Y","N"]
    falsify_scenario: str                  # P 피드백용 gap 텍스트
    mechanism_plausible: Literal["Y","P","N"]
    mechanism_gap: str
    clarity: Literal["Y","P","N"]
```
> C의 미해결쟁점(멀티프로바이더 Enum 강제력): Anthropic/OpenRouter/Gemini 별로 structured output 강제가 다르므로 **화이트리스트 정규식 폴백** 필수. Enum 밖 값 → 가장 보수적 등급(N)으로 처리.

---

## 3. 게이트 + 임계/등급 (R1 쟁점 ①②③ 확정)

**쟁점 ① LLM 채점 척도 → Y/P/N 확정.** 연속점수(C의 0~30, B의 5점) 전면 폐기. 게이트가 LLM 판정 위에 서므로 연속 스케일은 통과/미달을 동전던지기로 만든다. 3자 만장일치.

**쟁점 ② 통과 임계 + 중간등급 → 결격 게이트 우선 + 2단계 등급. 절대 임계는 봉인.**
A의 78점·C의 85점·B의 70점 모두 매직넘버 → 캘리브레이션 데이터 없이 절대값 정당화 불가(R1 3자 동의). v1은 **게이트 + 상대등급**으로만 출발하고, 임계는 잠정값으로 두되 게이트가 실질 품질을 보장한다.

| 등급 | 조건 | 루프 동작 |
|------|------|------|
| **PASS** | D1==20 **AND** D2==15 **AND** D3≥15 **AND** 총점 ≥ **80** | 루프 종료 → bias_screener |
| **PASS w/ CAVEAT** | D1·D2 게이트 통과 **AND** 총점 ≥ **68** (D3<15 또는 일부 약함) | **통과**하되 약점 차원을 caveat로 bias_screener·UI에 전달 |
| **REFINE** | 게이트 통과했으나 총점 < 68 | sharpener 재호출 (피드백 주입) |
| **REDESIGN** | **D1==0 OR D2==0** (게이트 결격) **OR** (D3<10 AND 총점<68) | §4 정체정책에 따라 처리 — 무한발산 방지 |

> **쟁점 ③ 핵심:** REDESIGN이라도 **Expander 롤백 안 함**(C 강력 주장 + A·B 동의). 컨텍스트 비대화 + 사용자 원의도 훼손 위험. 게이트 결격 시 **sharpener에 "결격 차원만 고쳐라" 강제 피드백**으로 최대 1회 재시도 후, 안 되면 Best-so-far Soft Pass.
> **중간등급 채택:** B의 "Acceptable with Caveat" 도입(3자 동의) — 단 **결격 게이트 필수 통과** 조건을 붙여 "측정·반증 없는데 통과" 모순 차단.

---

## 4. 정체 정책 (쟁점 ③ 확정: Best-so-far Soft Pass)

3중 차단, 어느 하나라도 걸리면 종료. **종료 시 항상 best-so-far(argmax 총점) 반환.**

```python
MAX_TURNS = {"quick": 2, "deep": 3}

def should_stop(history, mode):
    cur = history[-1]
    if cur.grade in ("PASS", "PASS_CAVEAT"):        return True, "pass"
    if len(history) >= MAX_TURNS[mode]:             return True, "max_turns→best-so-far soft pass"
    # 주신호: 동일 미달 차원 집합 2회 연속 (점수 Δ 아님 — R1 만장일치)
    if len(history) >= 2 and cur.failed_set == history[-2].failed_set:
        return True, "stall: 동일결손 반복→모델한계→best-so-far soft pass"
    # 보조신호: 동일 '룰' 차원만 2회 반복 (LLM 노이즈 배제, from C)
    if len(history) >= 2 and cur.failed_rule_dims and cur.failed_rule_dims == history[-2].failed_rule_dims:
        return True, "stall(rule): best-so-far soft pass"
    return False, "continue"
```

**정체 신호 채택 (쟁점 ③ 부속):**
- 주신호 = **동일 미달 차원 집합 반복**(A). 점수 Δ≤5(B·C 원안)는 LLM 노이즈로 ±5 흔들려 폐기.
- 보조신호 = **동일 룰 차원만 반복**(C) — LLM 변동을 배제한 순수 결정론 신호.
- 둘은 **OR**가 아니라 위계: 주신호 우선, 룰 신호는 LLM 판정이 흔들릴 때의 안전망.

**Expander 롤백 미채택 근거(쟁점 ③ 최종):** 정체·재설계 모두 **전진(Soft Pass)** 로 처리. Expander 되돌림은 (1)세션 컨텍스트 비대화 (2)사용자 원의도와 다른 가설로 발산 (3)비용 — 3중 리스크. 대신 caveat를 들고 다음 단계로 넘겨 사용자가 판단하게 한다.

---

## 5. 피드백 주입 (단조수렴 유도)

미달 차원 → `(차원, current_status, action_required)` JSON 배열(C 구조) + **"통과 차원은 건드리지 마라" 메타지시**(A·C 공통).

```json
{
  "refinement_directive": "다음 결손만 교정하고 통과한 차원은 수정하지 마시오.",
  "failed_dimensions": [
    {"dimension":"D3 메커니즘","current_status":"LLM: 개입→전환 사이 인지변화 누락(P)",
     "action_required":"마이크로 전환(클릭률·체류) 중간 노드를 mechanism_path에 추가"}
  ],
  "constraints": "잘 작성된 jtbd_reframe·통과 차원은 유지"
}
```

---

## 6. 비용·재현성

| 구성 | LLM 호출/턴 |
|------|:---:|
| 룰 채점 (D1,D4,D5 + D3구조 + D6모호어) | 0 |
| LLM 이진 판정 (D2·D3·D6 묶음 1콜) | 1 |

턴당 1콜 × 최대 3턴 = **최악 3콜.** 점수는 결정론, LLM은 이진 판정에만.

---

## 7. v1에서 의도적으로 봉인한 것 (정직)

1. **절대 임계 80/68은 잠정값.** 실제 가설 20~30개를 셋이 채점·캘리브레이션하기 전엔 정당화 불가. v1 운영 로그로 ROC 잡아 재조정.
2. **HypothesisOutput 필드 충족률 미검증.** `confounder_candidates` 등이 자주 빈 배열이면 룰 차원이 0점으로 쏠려 REDESIGN 폭증 → 상류 에이전트 출력 분포 먼저 측정.
3. **LLM 이진 판정의 경계 재현성.** Y/N 경계 케이스는 2회 채점 일치율 측정 필요.
4. **모델 전환 옵션 미채택.** "Claude가 못 고친 D3을 GPT에 넘기기"(B 제안)는 멀티모델 분업과 엮이는 별도 과제로 분리.

---

원하면 이 권고안을 그대로 `src/hypothesis/quality_scorecard.py` 구현으로 옮기고 기존 141개 테스트에 HQS 케이스를 추가하는 작업으로 바로 들어갈 수 있다. 진행할까?
