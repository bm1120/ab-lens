# ab-lens 구현 상태 (v8)

> hermes 에이전트 및 협업자용 진행 상황 문서.
> 설계 플랜: `~/.hermes/plans/2026-06-01_ab-lens.md` (v8)
> 최종 갱신: 2026-06-03 / 브랜치: `feat/v8-tab1-context-loop`

## 한눈에 보기

A/B 테스트 **설계(탭1) + 결과분석(탭2)** 웹앱. 1인 개발, 사용자 자격증명 입력.
핵심 차별점 = **Context Loop**(설계 약속 ↔ 분석 현실 대조로 peeking/체리피킹/MDE미달 차단).

- 코드 위치: `/Users/choeingyu/Documents/docker/ab-lens`
- 테스트: **98개 통과** (TDD)
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

| Provider | 자격증명 | 모델 | 비고 |
|---|---|---|---|
| **CLAUDE_CODE** (기본) | `CLAUDE_CODE_OAUTH_TOKEN` | `claude-haiku-4-5-20251001` | OAuth Bearer + `oauth-2025-04-20` 베타헤더, **구독=비용 0** |
| OPENROUTER | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4-5` | rate limit 시 대안 |
| ANTHROPIC | `ANTHROPIC_API_KEY` | (구형, deprecated) | |

- 실증: Claude Code OAuth로 가설고도화 파이프라인 4단계 end-to-end 성공 확인.
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
2d40e1c providers: Claude Code OAuth + 자격증명 자동로드 + 스키마 주입
d402b3a tab1-ui: 탭1 실험설계 UI + DesignContext 조립/설계서
4e34726 task-a: 탭1 가설 고도화 파이프라인
8e2a30a context-loop: 탭2에 Context Loop 연결
e20e8e3 task-d: v8 공통 기반 스키마 + Context Loop 가드
fbec852 baseline: ab-lens v1 (탭2 결과분석 MVP, 보존)
```

## 미구현 / 다음 단계

- [ ] 대안 선택 재실행 1회 제한 (UI 보조 기능)
- [ ] DesignAgent LLM 지표검토(Goodhart/FWER 코멘트) — 현재 deterministic 조립으로 대체
- [ ] DeepCritique 2라운드 (현재 Deep=편향 7종으로 단순화)
- [ ] 탭2 결과분석을 Claude Code OAuth로 end-to-end 검증 (탭1만 실증 완료)
- [ ] 실제 LLM 프롬프트 품질 튜닝 (단위테스트는 전부 mock)
- [ ] main 브랜치 머지 / PR
- [ ] (확장 로드맵 B) 다중사용자·API 제품화 시 FastAPI 백엔드 분리
