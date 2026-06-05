"""프로바이더 프롬프팅 진단 — Claude / GPT / Gemini 교차 비교 (재실행 가능).

축 A 포맷 견고성(결정론) · B 지시 준수(결정론 룰) · C 품질(★교차 모델 패널 채점).
자기 채점 금지: 각 프로바이더 출력은 나머지 두 프로바이더가 채점 → 평균.
"""
import json
import statistics as stat

from src.config import get_credential
from src.schemas import LLMProvider
from src.llm_client import call_llm
from src.llm_json import extract_json, _schema_instruction
from src.hypothesis.expander import ExpanderOutput, SYSTEM_KO as EXP_SYS
from src.hypothesis.sharpener import SYSTEM_KO as SHP_SYS, _build_prompt as shp_prompt
from src.design_schemas import HypothesisOutput
from src.hypothesis.quality_scorecard import judge_hypothesis, score_hypothesis
from src.hypothesis.scorecard_lexicons import direction_rx, vague_metric_set, norm_token

CC = get_credential("CLAUDE_CODE_OAUTH_TOKEN")
OR = get_credential("OPENROUTER_API_KEY")

# (라벨, provider, key, model)
PROVIDERS = [
    ("Claude", LLMProvider.CLAUDE_CODE, CC, "claude-haiku-4-5-20251001"),
    ("GPT",    LLMProvider.OPENROUTER, OR, "openai/gpt-5"),
    ("Gemini", LLMProvider.OPENROUTER, OR, "google/gemini-3.1-pro-preview"),
]

IDEAS = [
    "결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
    "온보딩에 진행률 바를 추가하면 가입 완료율이 오른다",
    "추천을 협업필터링으로 바꾸면 재방문율이 오른다",
]


def gen_raw(system, prompt, schema, provider, key, model):
    guided = system + _schema_instruction(schema)
    return call_llm(prompt=prompt, system=guided, api_key=key, provider=provider,
                    lang="ko", model=model, temperature=None)


def fmt_metrics(raw, schema):
    s = raw.strip()
    fence = "```" in raw
    clean_start = s.startswith("{")
    preamble = (not clean_start) and (not s.startswith("```"))
    json_ok = schema_ok = False
    parsed = None
    try:
        parsed = schema.model_validate(extract_json(raw))
        json_ok = True
        schema_ok = True
    except Exception:
        try:
            extract_json(raw); json_ok = True
        except Exception:
            pass
    return dict(fence=fence, preamble=preamble, json_ok=json_ok, schema_ok=schema_ok), parsed


def jtbd_ok(exp: ExpanderOutput) -> bool:
    t = exp.jtbd_reframe.lower()
    return ("want" in t and "so" in t) or ("하고 싶" in exp.jtbd_reframe and "할 수" in exp.jtbd_reframe)


def adherence(hyp: HypothesisOutput) -> dict:
    direction = bool(direction_rx("ko").search(hyp.sharpened_hypothesis))
    vague = vague_metric_set("ko")
    metric_ok = bool(hyp.suggested_primary_metric) and norm_token(hyp.suggested_primary_metric, "ko") not in vague
    mech_arrow = ("→" in hyp.mechanism_path) or ("->" in hyp.mechanism_path)
    return dict(direction=direction, metric_ok=metric_ok, mech_arrow=mech_arrow)


def run():
    rows = {p[0]: {"fence": [], "preamble": [], "json_ok": [], "schema_ok": [],
                   "jtbd": [], "direction": [], "metric_ok": [], "mech_arrow": [],
                   "xgate": [], "xqual": []} for p in PROVIDERS}
    hyps = {}   # (label, idx) -> HypothesisOutput (교차채점용)

    for idx, idea in enumerate(IDEAS):
        for label, prov, key, model in PROVIDERS:
            try:
                # expand
                er = gen_raw(EXP_SYS, idea, ExpanderOutput, prov, key, model)
                em, exp = fmt_metrics(er, ExpanderOutput)
                if exp is None:
                    exp = ExpanderOutput(jtbd_reframe=idea, implicit_assumptions=[], candidate_hypotheses=[idea])
                rows[label]["jtbd"].append(1 if jtbd_ok(exp) else 0)
                # sharpen
                sr = gen_raw(SHP_SYS, shp_prompt(idea, exp), HypothesisOutput, prov, key, model)
                sm, hyp = fmt_metrics(sr, HypothesisOutput)
                for m in ("fence", "preamble", "json_ok", "schema_ok"):
                    rows[label][m].append(1 if sm[m] else 0)
                if hyp is None:
                    print(f"  [{label}#{idx}] sharpen 파싱 실패 | len={len(sr)} fence={sm['fence']} | head={sr[:160]!r} | tail={sr[-120:]!r}")
                    continue
                hyp = hyp.model_copy(update={"raw_idea": idea})
                ad = adherence(hyp)
                for k in ("direction", "metric_ok", "mech_arrow"):
                    rows[label][k].append(1 if ad[k] else 0)
                hyps[(label, idx)] = hyp
                print(f"  [{label}#{idx}] fence={sm['fence']} pre={sm['preamble']} schema={sm['schema_ok']} dir={ad['direction']} metric={ad['metric_ok']}")
            except Exception as e:
                print(f"  [{label}#{idx}] 생성 실패: {type(e).__name__}: {str(e)[:120]}")

    # ── C. 교차 패널 채점 (자기 채점 금지) ──
    print("\n=== 교차 채점 ===")
    for idx in range(len(IDEAS)):
        for label, prov, key, model in PROVIDERS:
            hyp = hyps.get((label, idx))
            if hyp is None:
                continue
            judges = [(p, k, m) for (l, p, k, m) in PROVIDERS if l != label]  # 나머지 둘
            gates, totals = [], []
            for jp, jk, jm in judges:
                try:
                    j = judge_hypothesis(hyp, api_key=jk, provider=jp, lang="ko", model=jm)
                    sc = score_hypothesis(hyp, j, lang="ko")
                    gates.append(1 if sc.gate_passed else 0)
                    totals.append(sc.total)
                except Exception as e:
                    print(f"    judge {jp} 실패: {type(e).__name__}")
            if totals:
                rows[label]["xgate"].append(stat.mean(gates))
                rows[label]["xqual"].append(stat.mean(totals))
                print(f"  [{label}#{idx}] 교차게이트={stat.mean(gates):.2f} 교차품질={stat.mean(totals):.1f}")

    # ── 요약 표 ──
    def pct(xs):
        return f"{100*stat.mean(xs):.0f}%" if xs else "—"
    def avg(xs):
        return f"{stat.mean(xs):.1f}" if xs else "—"

    print("\n=== 진단 요약 ===")
    hdr = ["provider", "schema_clean", "fence", "preamble", "jtbd", "direction", "metric", "mech_arrow", "xgate", "xqual"]
    print(" | ".join(hdr))
    for label, *_ in PROVIDERS:
        r = rows[label]
        print(" | ".join([
            label, pct(r["schema_ok"]), pct(r["fence"]), pct(r["preamble"]),
            pct(r["jtbd"]), pct(r["direction"]), pct(r["metric_ok"]), pct(r["mech_arrow"]),
            (f"{100*stat.mean(r['xgate']):.0f}%" if r["xgate"] else "—"), avg(r["xqual"]),
        ]))
    print("\nJSON_DUMP=" + json.dumps({l: {k: (stat.mean(v) if v else None) for k, v in rows[l].items()} for l, *_ in PROVIDERS}, ensure_ascii=False))


if __name__ == "__main__":
    run()
