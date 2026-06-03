# 🔬 ab-lens

> **실험 설계 의도를 기억하고, 결과 해석 시 인지편향을 감지하는 유일한 도구**

A/B 테스트를 처음부터 끝까지 — 막연한 아이디어에서 날카로운 가설로, 설계에서 결과 해석까지.

---

## 왜 ab-lens인가

| 도구 | 가설 고도화 | 샘플 계산 | 편향 감지 | 설계→결과 이월 |
|---|---|---|---|---|
| Fibr / Personizely | ❌ | ✅ | ❌ | ❌ |
| CraftUpLearn | ❌ | ✅ | ❌ | ❌ |
| pvalue.net | ❌ | ✅ | ❌ | ❌ |
| **ab-lens** | ✅ | ✅ | ✅ | ✅ |

기존 도구들은 가설이 이미 완성됐다고 가정하고 통계 계산만 합니다.
ab-lens는 **"버튼 색을 바꾸면 클릭률이 오를 것 같다"** 수준의 아이디어에서 시작합니다.

---

## 핵심 기능

### 탭 1 — 실험 설계

**가설 고도화** (thinking-protocol 이식)
- 아이디어 입력 → JTBD 재프레이밍 → 암묵적 전제 드러내기
- 대안 가설 발산 (SCAMPER 구조)
- 메커니즘 검증: `개입 → 행동 변화 → 지표` 경로 명시
- 인지편향 스크리닝 (Confirmation Bias / Anchoring / Sunk Cost)
- Adversarial Refinement로 최종 가설 수렴
  - **Quick Mode** (~20초): 1라운드 수렴 + 메커니즘 명시
  - **Deep Mode** (~40초): 2라운드 DeepCritique — Round 2에서 반례 제시, 실패 조건 명시, 가설 강화 또는 대안 채택
- 대안 가설 선택 후 재실행 1회 제한 (과도한 탐색 방지)

**설계 파라미터 자동 추출**
- 고도화된 가설 → 지표·MDE·샘플 사이즈 구조화 JSON 자동 매핑
- 지표 타입 분기: 비율 / 연속형 / 카운트 / 클러스터 (ICC 포함)
- 설계서 Markdown 다운로드

### 탭 2 — 결과 분석

**Context Loop** ⭐ 핵심 해자
- 설계 시 합의한 약속(MDE·지표·샘플)과 실제 결과 대조
- **peeking** 배지: 샘플 미달 조기 종료 감지
- **metric_swap** 배지: 체리피킹 — 약속한 1차 지표가 아닌 지표가 유의
- **below_mde** 배지: 통계적 유의성은 있으나 실무적으로 무의미한 효과

**통계 분석**
- Two-proportion z-test, 검정력 분석, SRM(카이제곱) 감지
- FWER 보정 (Bonferroni), 설계 시 합의 alpha 자동 이월

**인지심리 기반 편향 감지** (논문 근거 매핑)
- 7개 편향 레퍼런스 풀 하드코딩 (Kahneman 2011, Simmons 2011, Kohavi 2020 등)
- 설계 시점 편향 경고 ↔ 결과 시점 편향 교차 참조

**의사결정 추천**
- 시나리오 3개 (출시 / 추가실험 / 조건부 출시) + 신뢰도

---

## 아키텍처

```
탭1: 아이디어 → [Trivial Router] → [가설 고도화 파이프라인]
                                        ↓ Quick(~20초) / Deep(~40초)
                                   HypothesisExpander (Framer+Ideator)
                                   HypothesisSharpener
                                     Quick: Round 1 수렴 + 메커니즘 명시
                                     Deep:  Round 1 + Round 2 DeepCritique
                                            (반례·실패조건·대안 채택)
                                   BiasScreener (Warning only)
                                        ↓
                               사실 수치 입력 (baseline, MDE, n)
                                        ↓
                               DesignContext + 설계서.md 생성
                               ab-design-context.json 다운로드
                                   ↓ (세션 자동 이월 또는 JSON 업로드)
탭2: 결과 수치 → [Context Loop 대조] → peeking/metric_swap/below_mde 배지
              → StatisticalAnalyst → BiasDetector → DecisionRecommender
              → 1페이지 브리핑
```

---

## 설치 & 실행

```bash
# uv 사용 (권장)
uv sync
uv run streamlit run app.py

# pip 사용
pip install -e .
streamlit run app.py
```

### LLM 설정

사이드바에서 API 키 입력 또는 `~/.hermes/.env`에 자동 로드:

```env
# Claude Code 구독 (비용 0, 권장)
CLAUDE_CODE_OAUTH_TOKEN=your_oauth_token

# 또는 OpenRouter
OPENROUTER_API_KEY=your_openrouter_key
```

| Provider | 모델 | 비용 |
|---|---|---|
| Claude Code OAuth | claude-haiku-4-5 | 구독 포함 (무료) |
| OpenRouter | claude-sonnet-4-5 | 사용량 과금 |

---

## 기술 스택

- **LLM**: Anthropic Claude (Claude Code OAuth / OpenRouter)
- **UI**: Streamlit (단일 앱, 탭 구조)
- **스키마**: Pydantic v2 (JSON Schema 프롬프트 주입으로 구조화 출력 강제)
- **통계**: scipy, statsmodels
- **테스트**: pytest, 104개 통과 (단위+통합, mock LLM) + LLM 실호출 e2e 별도 (TDD)

---

## 테스트

```bash
# 전체 (단위 + 통합, mock LLM)
uv run pytest tests/ -q

# 탭2 e2e (Claude Code OAuth 실제 호출 필요)
uv run pytest tests/test_tab2_e2e.py -v -s
```

---

## 배경

인지심리학 석사 + 신경과학 연구 → 의료 AI → 산업 데이터 분석 경로를 거치며,
실무에서 반복적으로 목격한 패턴:

- PM이 "버튼 색 바꾸면 클릭률 오를 것 같다"는 가설을 그대로 실험 설계에 올림
- 결과가 나오면 p=0.049를 "성공", p=0.051을 "샘플 더 모으자"로 해석
- 사전에 합의한 MDE나 지표가 분석 시점에 슬그머니 바뀜

이 도구는 [thinking-protocol-plugin](https://github.com/bm1120/thinking-protocol-plugin)의
`framer / ideator / bias-check / validator` 로직을 A/B 테스트 도메인에 이식한 것입니다.

---

## 로드맵

- [x] 가설 고도화 파이프라인 (Quick/Deep Mode)
- [x] Context Loop (peeking / metric_swap / below_mde)
- [x] 탭2 Claude Code OAuth e2e 검증
- [x] DeepCritique 2라운드 (Quick/Deep Mode 분기, Round 2 반례·실패조건·대안 채택)
- [x] 대안 가설 선택 재실행 1회 제한 UI
- [ ] LLM 프롬프트 품질 튜닝
- [ ] 다중 사용자 / API 제품화 (FastAPI 분리)

---

## 라이선스

MIT
