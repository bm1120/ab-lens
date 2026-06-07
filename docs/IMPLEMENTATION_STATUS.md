# ab-lens 구현 상태 (v8)

> hermes 에이전트 및 협업자용 진행 상황 문서.
> 설계 플랜: `~/.hermes/plans/2026-06-01_ab-lens.md` (v8)
> 최종 갱신: 2026-06-07 / 브랜치: `main` (PR #15까지 머지)

## 한눈에 보기

A/B 테스트 **설계(탭1) + 결과분석(탭2)** 웹앱. 1인 개발, 사용자 자격증명 입력.
핵심 차별점 = **Context Loop**(설계 약속 ↔ 분석 현실 대조로 peeking/체리피킹/MDE미달 차단).

- 코드 위치: `/Users/choeingyu/Documents/docker/ab-lens`
- 테스트: 단위/통합 **212개** + 골든셋 **12개**(실LLM, `pytest -m golden`)
- 실행: `streamlit run app.py` (사이드바 키 자동 로드, 입력 불필요)

## v8 아키텍처 결정 (3-모델 토론 Gemini/Codex/Claude 만장일치)

| 결정 | 내용 |
|---|---|
| 단일 Streamlit | FastAPI 분리 **철회**. LangGraph 미도입, in-process 직접 호출. (FastAPI는 확장 로드맵 B로 보류) |
| 탭간 이월 | `ab-design-context.json` 다운로드/업로드 + 같은 세션은 `st.session_state` 자동 연결 |
| 핵심 해자 | **Context Loop** (deterministic, LLM 아님, 비용 0). 문서포맷·JSON추출은 commodity로 격하 |
| 산출물 | 설계서 **Markdown** 우선 (.docx는 Phase 2) |

## 모듈 맵

```
src/
  config.py            ← ~/.hermes/.env 자격증명 자동 로드 (OS env 우선)
  schemas.py           ← (기존 v1) 탭2 결과분석 스키마 — 보존
  design_schemas.py    ← (v8) DesignContext(+to_json/from_json), HypothesisOutput,
                          BiasScreen*, SamplePlanOutput, DesignQuality
  design_stats.py      ← calculate_sample_size (proportion/continuous/count + cluster ICC)
  bias_pool.py         ← 편향 7종 레퍼런스 + BiasType enum 강제
  design_rubric.py     ← 필수/권고 점수화(합100) + grade
  context_loop.py      ← ★ContextLoopGuard (peeking/지표스왑/MDE미달) + build_observed_result
  llm_client.py        ← call_llm: ANTHROPIC / CLAUDE_CODE(OAuth) / OPENROUTER
  llm_json.py          ← call_structured: JSON Schema 프롬프트 주입 + 파싱/검증
  hypothesis/          ← 탭1 Stage 1~2
    trivial_router.py  ← Just Do It 판정
    expander.py        ← 발산 (JTBD + 대안 3개)
    sharpener.py       ← 수렴 + 메커니즘 → HypothesisOutput
    bias_screener.py   ← 설계 편향 (Quick 3종/Deep 7종, Warning only)
    pipeline.py        ← 직접 오케스트레이션 (Quick/Deep, 팀합의 스킵, on_progress)
  design/              ← 탭1 Stage 3
    assembler.py       ← HypothesisOutput + 사실수치 → DesignContext (deterministic)
    doc_generator.py   ← 설계서 Markdown 생성 (수치 인용만)
app.py                 ← 3탭: 🧪실험설계 / 결과입력 / 결과브리핑
```

## LLM Provider 세팅

`~/.hermes/.env`의 자격증명을 자동 로드한다 (사이드바 입력 불필요).

모델 ID는 표기가 provider마다 다르다 (2026-06-03 실제 검증):
- Claude Code(OAuth)/Anthropic = **하이픈** 표기 (`claude-sonnet-4-5`)
- OpenRouter = **점** 표기 (`anthropic/claude-sonnet-4.5`)

| Provider | 자격증명 | 기본 모델 | 선택 가능 | 비고 |
|---|---|---|---|---|
| **CLAUDE_CODE** (기본) | `CLAUDE_CODE_OAUTH_TOKEN` | `claude-haiku-4-5-20251001` | haiku-4-5 / sonnet-4-5 / sonnet-4-6 / opus-4-5 / opus-4-8 | OAuth Bearer + `oauth-2025-04-20` 베타헤더, **구독=비용 0**. haiku만 200 확인, 상위는 구독 한도에 따라 429 가능(ID는 유효) |
| OPENROUTER | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4.5` | sonnet-4.5/4.6 · haiku-4.5 · opus-4.8 · gpt-4o(-mini) · llama-3.3-70b | 카탈로그 `/models` 검증, 실호출 OK |
| ANTHROPIC | `ANTHROPIC_API_KEY` | `claude-haiku-4-5-20251001` | haiku-4-5 / sonnet-4-6 / opus-4-8 | 구형 3.5/3.7(EOL) 제거 |

- 사이드바에서 provider별 모델 **드롭다운 선택** 지원.
- ⚠️ 모델 ID 검증 결과(2026-06-03): `claude-sonnet-4-5-20251001`, `claude-opus-4-5-20251001`(404)과 OpenRouter 하이픈 표기(`anthropic/claude-sonnet-4-5`, 404)는 **잘못된 ID였고 수정됨**.
- 실증: Claude Code OAuth로 가설고도화 파이프라인 4단계 end-to-end 성공 + OpenRouter sonnet-4.5 실호출 성공.
- `call_structured`가 Pydantic JSON Schema를 프롬프트에 주입 → 필드명 불일치/파싱 깨짐 방지.
- `max_tokens=4096` (큰 구조화 출력 잘림 방지).

## 전체 흐름 (작동)

```
탭1: 아이디어 → [trivial→발산→수렴→편향] → 사실수치 입력
   → DesignContext + 설계서.md + ab-design-context.json
        ↓ (session_state 자동 / 또는 json 업로드)
탭2: 결과수치 → [Context Loop 대조] → peeking/지표스왑/MDE미달 배지
   → 통계분석 → 편향감지(탭1 교차참조) → 추천
```

## 커밋 히스토리 (feat/v8-tab1-context-loop)

```
e761c1b docs: v8 구현 상태 문서 (hermes 에이전트/협업자용)
2d40e1c feat(providers): Claude Code OAuth + 자격증명 자동로드 + 스키마 주입
d402b3a feat(tab1-ui): 탭1 실험설계 UI + DesignContext 조립/설계서 (TDD)
4e34726 feat(task-a): 탭1 가설 고도화 파이프라인 (TDD, 직접 오케스트레이션)
8e2a30a feat(context-loop): 탭2에 Context Loop 연결 (json 업로드→위반 배지)
e20e8e3 feat(task-d): v8 공통 기반 스키마 + Context Loop 가드 (TDD)
fbec852 baseline: ab-lens v1 (탭2 결과분석 MVP)
```

## 완료 ✅

- **Task D** — 공통 기반: `design_schemas.py`, `design_stats.py`, `bias_pool.py`, `design_rubric.py`, `context_loop.py`, `llm_client.py`, `llm_json.py`
- **Task A** — 탭1 가설 고도화: `hypothesis/` (trivial_router / expander / sharpener / bias_screener / pipeline)
- **Context Loop** — `ContextLoopGuard` (peeking / 지표스왑 / MDE미달 배지, deterministic, 비용 0)
- **탭1 UI** — DesignContext 조립 + 설계서 Markdown 생성
- **Provider** — Claude Code OAuth (구독=비용 0) + OpenRouter 대안 + 자격증명 자동 로드
- **탭2 Context Loop 연결** — JSON 업로드 → 위반 배지
- **탭2 e2e 검증** — Claude Code OAuth 실제 호출, 8개 시나리오 106/106 통과

## 미구현 / 다음 단계 🔲

- [x] ~~탭2 결과분석 Claude Code OAuth end-to-end 검증~~ ✅ **완료** (c0e9490)
- [x] ~~DesignAgent LLM 지표검토(Goodhart/FWER/effect_size/proxy/guardrail)~~ ✅ **완료** (PR #9, 효과크기 중심)
- [x] ~~DeepCritique 2라운드~~ ✅ **완료** — `sharpener.py` Deep 모드 1라운드 수렴 + 2라운드 적대적 비평. `test_sharpener.py` 10개로 검증(과거 문서가 stale했음)
- [x] ~~효과크기 중심 통계 철학~~ ✅ **완료** — 탭1 지표검토 + 탭2 95% CI·p값 강등 (PR #9·#10)
- [x] ~~다양 가설 생성(멀티-롤·하이브리드 멀티프로바이더)~~ ✅ **완료** (PR #11)
- [x] ~~프로바이더 어댑터(추론 모델 절단 방지)~~ ✅ **완료** (PR #12, `provider-prompting-diagnostic.md`)
- [x] ~~대안 선택 재실행 1회 제한~~ ✅ **완료** — `app.py` `rerun_count >= 1` enforce
- [x] ~~실제 LLM 프롬프트 품질 **골든셋** 회귀~~ ✅ **완료** — `pytest -m golden`, `tests/golden/` 12개 시나리오(실LLM 5회 ≥4), 평소 제외(addopts `-m 'not golden'`)
- [x] ~~**추상 구성개념 → 개념적·조작적 정의화**~~ ✅ **완료 (PR #15 머지, 2026-06-07)** — classify(clear/abstract/mixed) → measurement(개념정의+탭2호환 지표후보) → 측정확인 패널(개념정의 편집+지표선택+primary명시+취소) → sharpen(pinned 프롬프트 주입). 5페이즈 각 멀티모델 리뷰 반영. 모듈: `hypothesis/classify.py`·`measurement.py`, `pipeline.resume_with_pinned`
- [ ] **▶ 다음 작업: diverse 초안 → 탭2 이월 가드레일** — spec: `docs/design/diverse-carryover-guardrail.md`. diverse(빠른 초안, 측정확인 제외) 가설이 추상인데 측정 미확인 상태로 탭2 이월되는 것 방지. 관문 = 설계 확정(`app.py:726` assemble_design_context). 권장: soft 경고 + 측정확인 바로가기. 브랜치 `feat/diverse-carryover-guardrail`
- [ ] (확장 로드맵 B) 다중사용자·API 제품화 시 FastAPI 백엔드 분리

> 범용 도구: 멀티모델 리뷰 워크플로(Gemini+Codex 병렬→Claude 가중치 종합)를 `~/.claude/skills/multi-model-review` 스킬로 패키징.
