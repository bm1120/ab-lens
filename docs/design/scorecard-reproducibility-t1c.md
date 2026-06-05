# T1c — 룰가이드 LLM judge 재현성 측정 + 하드닝

> §8.3 봉인 항목("LLM 이진 판정 경계 재현성") 검증. 같은 가설을 K회 판정해 필드별 다수결 일치율 측정.
> 핵심 질문: **게이트(D2 반증)가 호출마다 흔들려 좋은 가설이 통과/탈락을 오가는가?**

## 방법
- 품질이 다른 가설 6개(명확/경계/약함, 경계 케이스 포함) × 각 5회 판정(haiku 기본).
- 필드별 다수결 일치율 + 게이트 결과 안정성 측정. (`/tmp/t1c_reproducibility.py` 재실행 가능)

## 결과 (temperature 하드닝 전 → 후)
| 필드 | 기본(API default temp) | **temperature=0** | 게이트 여부 |
|---|---|---|---|
| falsifiable | 93% | **97%** | ★ 게이트 |
| mechanism_plausible | 100% | 100% | |
| confound_relevant | 97% | 97% | |
| tradeoff_real | 90% | 90% | |
| clarity | 80% | 83% | 비게이트(등급) |
| alt_justified | 80% | 87% | 비게이트(등급) |

- **게이트 흔들린 가설: 1/6** (전·후 동일). 흔들린 건 *"UI를 개선하면 사용자 경험이 좋아진다"* — 방향·반증이 **본질적으로 모호한 가설**. temperature=0로 일치율 60%→80%로 개선됐으나 완전 안정은 아님(경계 가설은 흔들리는 게 어느 정도 타당).
- **명확한 가설(clear_good 등)은 전부 게이트 100% 안정.**

## 하드닝 (반영)
- **judge를 `temperature=0`(결정론)으로 호출** → 게이트 필드 93%→97%, 흔들리던 경계 케이스 60%→80%.
- 구현: `call_structured`/`call_llm`/`_call_*`에 옵셔널 `temperature` 추가(기본 None=현행 유지, 하위호환). `judge_hypothesis`만 `temperature=0.0` 사용.

## 결론 / 권고
1. **게이트는 명확한 가설에 신뢰 가능**(100%). 흔들림은 **본질적으로 모호한 가설**에 국한(80%) → 그런 경우는 어차피 REFINE/사용자 확인이 맞음.
2. clarity(83%)·alt_justified(87%)는 **비게이트 등급 차원**이라 등급 지터만 유발(통과/탈락 결정 아님). 허용 가능.
3. 추가 안정화가 필요하면(선택): ①게이트 필드에 **다수결 3회**(비용 3배) ②judge 모델을 **sonnet**으로(haiku 대비 ↑). 현재 temperature=0로 충분.

## 후속(T1c-followup) — 판정/생성 모델 분리

T1c 재현성은 **Haiku 기준**으로 측정됐다. 사용자가 생성 품질을 위해 모델을 Sonnet/Opus로 올리면
판정도 같이 끌려가 이 검증 전제가 깨지는 문제가 있었다(단일 셀렉터 커플링).

**해결**: 판정을 생성과 분리. `judge_hypothesis(model=None)`이면 `llm_client.judge_model_for(provider)`로
**provider별 Haiku를 고정**(CLAUDE_CODE/ANTHROPIC=`claude-haiku-4-5-20251001`, OPENROUTER=`anthropic/claude-haiku-4.5`).
`quality_loop`는 판정에 생성 model을 더 이상 넘기지 않는다. 명시적 model 전달 시에만 오버라이드.

- 효과: 생성=사용자 선택(추론↑), 판정=항상 Haiku temp=0(T1c 검증값·저비용·결정론 보존, 루프 매 턴 비용 폭증 방지).
- 회귀: `test_judge_pins_to_haiku_regardless_of_generation_model`, `test_judge_explicit_model_overrides_pin`.

## 봉인 해제 상태
§8.3 "LLM 이진 판정 재현성 미검증" → **측정 완료**. 게이트는 명확 케이스 100%·경계 80%, temperature=0 적용. 절대임계(80/68)는 여전히 봉인(별도 캘리브레이션 필요).
