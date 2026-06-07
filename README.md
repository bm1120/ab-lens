# 🔬 ab-lens

> **실험 설계 의도를 기억하고, 결과 해석 시 인지편향을 감지하는 유일한 도구**

A/B 테스트를 처음부터 끝까지 — 막연한 아이디어에서 날카로운 가설로, 설계에서 결과 해석까지.

---

## 왜 ab-lens인가

| 도구 | 가설 고도화 | 측정 타당도 | 샘플 계산 | 편향 감지 | 설계→결과 이월 |
|---|---|---|---|---|---|
| Fibr / Personizely | ❌ | ❌ | ✅ | ❌ | ❌ |
| CraftUpLearn | ❌ | ❌ | ✅ | ❌ | ❌ |
| pvalue.net | ❌ | ❌ | ✅ | ❌ | ❌ |
| **ab-lens** | ✅ | ✅ | ✅ | ✅ | ✅ |

기존 도구들은 가설이 이미 완성됐다고 가정하고 통계 계산만 합니다.
ab-lens는 **"버튼 색을 바꾸면 클릭률이 오를 것 같다"** 수준의 아이디어에서 시작합니다.

---

## 핵심 기능

### 탭 1 — 실험 설계

**가설 고도화** (thinking-protocol 이식)
- 아이디어 입력 → JTBD 재프레이밍 → 암묵적 전제 드러내기 → 대안 가설 발산
- 메커니즘 검증: `개입 → 행동 변화 → 지표` 경로 명시
- 인지편향 스크리닝 (Quick 3종 / Deep 7종, Warning only)
- Adversarial Refinement로 최종 가설 수렴
  - **Quick Mode** (~20초): 1라운드 수렴 + 메커니즘 명시
  - **Deep Mode** (~40초): 2라운드 DeepCritique — 반례 제시, 실패 조건 명시, 가설 강화 또는 대안 채택

**가설품질 스코어카드(HQS) + 멀티턴 고도화 루프**
- **게이트**: 측정가능성(D1)·반증가능성(D2)을 통과 못 하면 총점 무관 차단
- **6차원 품질**(측정·반증·메커니즘·정렬리스크·대안탐색·명료성) — 룰가이드 LLM judge(Haiku, temperature=0 결정론)
- 게이트 통과·정체까지 **자동 재고도화 반복**, best-so-far 채택
- 사용자 친화 등급 표시 (✅ 통과 / 🟡 조건부 / 🔁 보강 / 🔴 재설계)

**다양 가설 생성** (멀티-롤 · 하이브리드 멀티프로바이더)
- 4개 롤(공격적 성장·리스크 회피·메커니즘 순수주의·역발상)로 서로 다른 가설 발산 → 스코어카드로 선별·랭킹
- 자격증명이 여러 개면 롤을 **벤더에 분산**(Claude·GPT·Gemini) → 진짜 멀티프로바이더

**도메인 인테이크**
- 멀티턴 시 도메인 맥락이 부족하면 **타겟 질문** 후 고도화(서비스 유형·타겟·목표·제약)

**추상 구성개념 측정 타당도** (개념적 → 조작적 정의화)
- "브랜드 신뢰·인지도" 같은 추상 구성개념을 자동 감지(`classify`: 명확/추상/혼합) → **개념적 정의 + 탭2 호환 측정지표 후보** 제시(측정확인 패널)
- 개념 정의 편집 · 지표 선택 · 1차 지표 명시 후 그 지표로 **고정(pinned) 재고도화** — 측정 타당도(이 지표가 개념을 제대로 재는가)를 사용자가 확정
- 설문/장기 귀인처럼 A/B로 직접 측정 어려운 지표는 비호환 표시 + 대리지표 Goodhart 경고
- **이월 가드레일**: `diverse`(빠른 초안, 측정확인 제외) 등 측정 미확인 추상 가설이 설계 확정 시 → soft 경고 + `[측정 확인하기]` 바로가기(차단 없음). 측정 타당도 미검증 가설이 결과분석으로 새는 것 방지

**설계 파라미터 + DesignAgent 지표검토**
- 고도화된 가설 → 지표·MDE·샘플 사이즈 구조화 JSON 자동 매핑 (지표 타입: 비율/연속형/카운트/클러스터, ICC 포함)
- **LLM 지표검토**(advisory): effect_size·Goodhart(지표 게이밍)·FWER(다중검정)·proxy·guardrail 위험 정성 코멘트 — **효과크기 중심**(p값 과신 차단), 수치 미생성
- 대안 가설 선택 후 재실행 1회 제한 (과도한 탐색 방지)
- 설계서 Markdown + `ab-design-context.json` 다운로드

### 탭 2 — 결과 분석

**Context Loop** ⭐ 핵심 해자
- 설계 시 합의한 약속(MDE·지표·샘플)과 실제 결과 대조
- **peeking** 배지: 샘플 미달 조기 종료 감지
- **metric_swap** 배지: 체리피킹 — 약속한 1차 지표가 아닌 지표가 유의
- **below_mde** 배지: 통계적 유의성은 있으나 실무적으로 무의미한 효과

**통계 분석** (효과크기 중심)
- Two-proportion z-test, 검정력 분석, SRM(카이제곱) 감지
- **효과 크기 95% 신뢰구간** 노출 — p값(이분법 유의성)보다 효과크기·실질적 유의성·CI를 우선
- 추천 LLM도 "유의해도 CI가 0 포함/MDE 미달이면 출시 신중, 대형표본 p값 과신 금지" 원칙 적용

**인지심리 기반 편향 감지** (논문 근거 매핑)
- 7개 편향 레퍼런스 풀 하드코딩 (Kahneman 2011, Simmons 2011, Kohavi 2020 등)
- 설계 시점 편향 경고 ↔ 결과 시점 편향 교차 참조

**의사결정 추천**
- 시나리오 3개 (출시 / 추가실험 / 조건부 출시) + 신뢰도

---

## 아키텍처

```
탭1: 아이디어 → [Trivial Router] → [도메인 인테이크(맥락 부족 시 질문)]
        │     ↳ [추상 구성개념?] → 측정확인 패널(개념정의+지표후보 pin) → 고정 재고도화
        ├─ 단일 고도화: Expander → Sharpener(Quick 1R / Deep 2R DeepCritique) → BiasScreener
        │     ↳ 멀티턴 루프: sharpen → judge → 스코어카드(게이트+6차원) → 피드백 재고도화 (통과까지)
        └─ 다양 탐색: 4롤 × (expand→sharpen→judge→score) → 게이트·총점 랭킹
                      (하이브리드: 키 여러 개면 Claude·GPT·Gemini 벤더 분산)
                                        ↓ 가설 채택
                               사실 수치 입력 (baseline, MDE, n)
                                        ↓
                               DesignAgent 지표검토(effect_size/Goodhart/FWER/…)
                               [설계 확정] → 이월 가드레일(측정 미확인 추상이면 soft 경고)
                               DesignContext + 설계서.md + ab-design-context.json
                                   ↓ (세션 자동 이월 또는 JSON 업로드)
탭2: 결과 수치 → [Context Loop 대조] → peeking/metric_swap/below_mde 배지
              → StatisticalAnalyst(효과크기 95% CI) → BiasDetector → DecisionRecommender
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

# OpenRouter — GPT/Gemini 포함, 다양생성 벤더 분산용
OPENROUTER_API_KEY=your_openrouter_key
```

| Provider | 모델 예 | 비용 |
|---|---|---|
| Claude Code OAuth | claude-haiku/sonnet/opus | 구독 포함 (무료) |
| OpenRouter | claude / openai/gpt-5.x / google/gemini-3.x | 사용량 과금 |

**모델 분리**: 생성·구체화는 사용자가 고른 모델(추론 필요 → Sonnet/Opus 권장), 품질 **판정은 항상 Haiku temperature=0**으로 고정(저비용·재현성). **다양 탐색**은 키가 여러 개면 롤을 벤더에 분산해 진짜 멀티프로바이더로 동작.

**프로바이더 어댑터**: 추론 모델(gpt-5 등)의 출력 절단을 방지 — OpenRouter max_tokens 상향 + 절단 감지(`finish_reason`/`stop_reason`) + 파싱 1회 재시도. (근거: `docs/design/provider-prompting-diagnostic.md`)

---

## 기술 스택

- **LLM**: 멀티프로바이더 — Claude(Code OAuth) · GPT · Gemini (OpenRouter). 판정은 Haiku temp=0 핀, 추론 모델 절단 어댑터
- **UI**: Streamlit (단일 앱, 탭 구조)
- **스키마**: Pydantic v2 (JSON Schema 프롬프트 주입으로 구조화 출력 강제)
- **통계**: scipy, statsmodels (효과크기 95% CI 포함)
- **테스트**: pytest, 215개 통과 (단위+통합, mock LLM) + **골든셋 회귀** 12개(실LLM 5회 ≥4) + 탭2 e2e 별도 (TDD)

---

## 테스트

```bash
# 전체 (단위 + 통합, mock LLM) — 골든셋은 기본 제외(addopts -m 'not golden')
uv run pytest -q

# 프롬프트 품질 골든셋 회귀 (실LLM 5회 반복 ≥4 통과, CLAUDE_CODE_OAUTH_TOKEN 필요)
uv run pytest -m golden

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
- [x] DeepCritique 2라운드 (Round 2 반례·실패조건·대안 채택)
- [x] 대안 가설 선택 재실행 1회 제한 UI
- [x] 가설품질 스코어카드(HQS) + 멀티턴 고도화 루프
- [x] 도메인 인테이크 (맥락 부족 시 질문)
- [x] DesignAgent LLM 지표검토 (effect_size/Goodhart/FWER/proxy/guardrail)
- [x] 효과크기 중심 통계 (탭2 95% CI, p값 강등)
- [x] 다양 가설 생성 (멀티-롤 · 하이브리드 멀티프로바이더)
- [x] 프로바이더 어댑터 (추론 모델 절단 방지 — 측정 기반)
- [x] LLM 프롬프트 품질 **골든셋** 회귀 (`pytest -m golden`, 실LLM 5회 ≥4)
- [x] 추상 구성개념 **개념적 → 조작적 정의화** (측정확인 패널, pinned 재고도화)
- [x] diverse 초안 → 탭2 **이월 가드레일** (설계 확정 시 측정 타당도 soft 경고)

**백로그** (현재 진행 안 함)
- [ ] 다중 사용자 / API 제품화 (FastAPI 분리) — 단일 사용자 도구로는 불필요, 요구 발생 시 착수

---

## 라이선스

MIT
