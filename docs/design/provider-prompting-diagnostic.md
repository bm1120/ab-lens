# 프로바이더 프롬프팅 진단 (Claude · GPT · Gemini)

> 하이브리드 다양생성이 롤을 벤더에 분산하면서 "롤 차이 vs 프로바이더 차이"가 교란됨.
> 같은 구조화 과제를 3사에 던져 어디서 갈리는지 실측 → 꼭 필요한 어댑터만 설계(추측 배제).
> 재실행: `PYTHONPATH=. uv run python scripts/provider_diagnostic.py`

## 방법
- 대상: Claude(`claude_code`/haiku) · GPT(`openrouter`/`openai/gpt-5`) · Gemini(`openrouter`/`google/gemini-3.1-pro-preview`)
- 과제: 고정 아이디어 3개 × `expand`+`sharpen`(실제 파이프라인 단계)
- 축 **A 포맷 견고성**(결정론) · **B 지시 준수**(스코어카드 룰, 결정론) · **C 품질**(★교차 패널 채점 — 각 출력은 *나머지 두* 프로바이더가 채점, 자기 채점 금지)
- 유일 변수 = 생성 프로바이더. 심판은 항상 비-자기.

## 결과
| provider | schema clean | fence | preamble | jtbd | direction | metric | mech→ | 교차게이트 | 교차품질 |
|---|---|---|---|---|---|---|---|---|---|
| Claude(haiku) | 100% | **100%** | 0% | 100% | 100% | 100% | 100% | 83% | 86.7 |
| GPT(gpt-5) | **33%** 🔴 | 0% | 0% | 100% | 100% | 100% | 100% | 100% | 96.5 |
| Gemini(3-pro) | 100% | 0% | 0% | 100% | 100% | 100% | 100% | 100% | 91.8 |

## 발견 (가설과 다름)
1. **truncation이 지배적 문제 — 프롬프트 문구 아님.** GPT는 큰 스키마(`HypothesisOutput`) sharpen에서 2/3가 **JSON 중간 절단**으로 파싱 실패. raw가 닫는 중괄호 없이 문자열 중간에서 끊김(len 876·1624자).
   - 원인: `_call_openrouter`가 `max_tokens=4096` 고정 전송 + **finish_reason 미확인**. gpt-5는 추론 모델이라 추론 토큰이 예산을 잠식 → 출력 JSON 미완성. 절단 응답이 조용히 반환됨.
2. **같은 truncation이 판정(judge)에서도 발생.** 로그에 judge 출력이 `mechanism_gap`에서 절단 → 비관적 N 폴백. 이게 **Claude#1의 65점(게이트 0.5)을 끌어내린 아티팩트**(Claude 품질이 아니라 심판 절단 탓).
3. **지시 준수는 3사 모두 100%**(direction/metric/mechanism/jtbd) → **프롬프트 문구의 프로바이더별 분기는 불필요.**
4. **Claude는 항상 ` ```json ` 펜스**로 감쌈(extract_json이 처리해 무해), Gemini는 깔끔한 bare JSON, GPT는 펜스 없음.
5. **품질(C)은 교란됨**: Claude만 haiku(하위 티어) → 86.7은 공정 비교 아님. 게다가 위 #2 심판 절단 아티팩트 포함. 따라서 "Claude가 품질 낮다" 결론 금지 — 진짜 신호는 **포맷/절단**.

## 권장 어댑터 (데이터 기반 — "다른 프롬프트"가 아니라 생성 파라미터·견고성)
1. **프로바이더별 `max_tokens`**: OpenRouter(특히 추론 모델 gpt-5 등)는 8192+로 상향. Anthropic/Claude는 현행 유지 가능.
2. **truncation 감지**: `finish_reason == "length"`면 절단된 JSON을 조용히 반환하지 말고 **재시도(상향 예산)하거나 명확히 실패** 처리.
3. **파싱 견고성**: `call_structured`에 JSON 파싱 실패 시 **1회 재시도**(전이성 절단 완화). judge에도 동일 적용(아티팩트 N 폴백 감소).
4. **Claude 펜스**: 이미 extract_json이 처리 — 변경 불필요(단, 파싱 로직 변경 시 펜스 호환 유지).
5. **하지 말 것**: 프롬프트 *문구*를 프로바이더별로 분기(지시 준수 100%라 이득 없음, 유지보수만 늘어남).

## 어댑터 적용 결과 (검증)
`MAX_TOKENS_OPENROUTER=8192` + 절단 감지(`finish_reason=length`/`stop_reason=max_tokens`/content 없음 → `TruncatedResponseError`) + `call_structured` 1회 재시도 적용 후 재측정:

| provider | schema clean | 교차게이트 | 교차품질 |
|---|---|---|---|
| Claude | 100% (100%) | **100%** (83%→) | 88.0 (86.7→) |
| GPT | **100%** (**33%→**) ✅ | 100% | 91.5 (96.5→) |
| Gemini | 100% (100%) | 100% | 91.5 (91.8→) |

- **GPT 절단 해소: schema 33% → 100%**(다양생성에서 GPT 후보가 통째로 누락되던 문제 제거).
- **교차게이트 전 프로바이더 100%** — Claude#1의 65점(심판 절단 아티팩트) 소멸 → 품질 비교가 공정·안정화.
- content=None 전이성(Gemini 1회)도 `TruncatedResponseError` 재분류로 재시도 처리.

## 봉인/한계
- Claude를 동급 티어(sonnet/opus)로 재측정하면 품질(C) 공정 비교 가능(현재 haiku 핸디캡). 단 이번 목적(포맷·견고성 튜닝)에는 영향 없음.
- 교차 품질 점수는 심판 절단을 고치기 전(어댑터 적용 전) 값이라, 어댑터 후 재측정 시 상향·안정화 예상.
