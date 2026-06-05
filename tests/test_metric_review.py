"""DesignAgent LLM 지표검토 테스트 — 스키마 강건성 + 호출 계약 + 폴백 + 조립/렌더 통합.

실제 LLM 호출 없음(_call 주입). judge_hypothesis 와 동일 패턴.
"""
import pytest

from src.design_schemas import (
    BiasScreenResult, DesignContext, HypothesisOutput,
    MetricRisk, MetricReview, RejectedAlternative,
)
from src.design.assembler import DesignFacts, assemble_design_context
from src.design.doc_generator import render_design_doc
from src.design.metric_review import review_metrics


def mk_hyp(**ov) -> HypothesisOutput:
    base = dict(
        raw_idea="결제 버튼 색", jtbd_reframe="빠른 결제",
        implicit_assumptions=["색이 주목도에 영향"],
        mechanism_path="버튼 색 변경 → 주목도 상승 → 클릭 → 전환",
        confounder_candidates=["시즌성"],
        measurability_confirmed=True,
        sharpened_hypothesis="결제 버튼 색을 빨강으로 바꾸면 전환율이 증가한다",
        suggested_primary_metric="전환율",
        suggested_secondary_metrics=["클릭률", "체류시간", "스크롤깊이"],
        predicted_tradeoff_metrics=[],
        experiment_feasible=True,
        rejected_alternatives=[RejectedAlternative(hypothesis="크기", rejection_reason="작음")],
    )
    base.update(ov)
    return HypothesisOutput(**base)


def mk_facts(**ov) -> DesignFacts:
    base = dict(metric_type="proportion", baseline=0.1, agreed_mde=0.05)
    base.update(ov)
    return DesignFacts(**base)


# ── 스키마 강건성 (LLM 쓰레기 입력 강제) ──────────────────────────────
def test_risk_coerces_bad_kind_and_severity():
    r = MetricRisk(metric="전환율", kind="totally_wrong", severity="critical", note="x")
    assert r.kind == "goodhart" and r.severity == "medium"


def test_risk_severity_aliases():
    assert MetricRisk(kind="fwer", severity="hi", note="x").severity == "high"
    assert MetricRisk(kind="fwer", severity="med", note="x").severity == "medium"


def test_review_empty_default():
    mr = MetricReview()
    assert mr.risks == [] and mr.summary == ""


def test_risk_accepts_effect_size_kind():
    # 효과크기 중심 — effect_size 는 일급 kind (p값 보정보다 효과크기 추정 우선)
    r = MetricRisk(metric="전환율", kind="effect_size", severity="high",
                   note="MDE 미만 효과도 p<0.05 가능 → 효과크기+CI 보고 권고")
    assert r.kind == "effect_size"


# ── 호출 계약 ─────────────────────────────────────────────────────────
def test_review_passes_counts_and_uses_temp_zero():
    cap = {}

    def grab(**kw):
        cap.update(kw)
        return MetricReview(risks=[MetricRisk(metric="전환율", kind="fwer", note="보정 권고")])

    out = review_metrics(mk_hyp(), metric_type="proportion", api_key="k",
                         provider=None, _call=grab)
    assert out.risks[0].kind == "fwer"
    assert cap["temperature"] == 0.0
    # 2차 지표 3개가 프롬프트에 반영(FWER 신호)
    assert "3" in cap["prompt"]


def test_prompt_centers_effect_size_over_pvalue():
    # 통계 철학: p값 보정보다 효과크기·MDE·신뢰구간 중심
    cap = {}

    def grab(**kw):
        cap.update(kw)
        return MetricReview()

    review_metrics(mk_hyp(), metric_type="proportion", api_key="k", provider=None, _call=grab)
    p, s = cap["prompt"], cap["system"]
    assert "효과크기" in p and "MDE" in p and "신뢰구간" in p
    assert "effect_size" in p            # 일급 kind 안내 포함
    assert "추정" in p                    # FWER 무게중심 = 추정(보정 아님)
    assert "효과크기" in s                 # system 도 효과크기 중심 명시


def test_review_respects_selected_model_not_pinned():
    # 검토는 추론 필요 → 호출자 model 그대로 전달(Haiku 핀 아님)
    cap = {}

    def grab(**kw):
        cap.update(kw)
        return MetricReview()

    review_metrics(mk_hyp(), metric_type="proportion", api_key="k",
                   provider=None, model="claude-opus-4-8", _call=grab)
    assert cap["model"] == "claude-opus-4-8"


def test_review_fallback_on_exception():
    def boom(**kw):
        raise RuntimeError("api down")

    out = review_metrics(mk_hyp(), metric_type="proportion", api_key="k",
                         provider=None, _call=boom)
    assert isinstance(out, MetricReview) and out.risks == []


# ── 조립 통합 ─────────────────────────────────────────────────────────
def test_assembler_attaches_review():
    mr = MetricReview(risks=[MetricRisk(metric="(전체)", kind="guardrail", note="guardrail 없음")])
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts(),
                                  metric_review=mr)
    assert ctx.metric_review is mr


def test_assembler_review_optional():
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts())
    assert ctx.metric_review is None


# ── 직렬화 (Context Loop 이월) ────────────────────────────────────────
def test_design_context_json_roundtrip_with_review():
    mr = MetricReview(risks=[MetricRisk(metric="클릭률", kind="goodhart", severity="high", note="게이밍")],
                      summary="다중검정 주의")
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts(),
                                  metric_review=mr)
    back = DesignContext.from_json(ctx.to_json())
    assert back.metric_review.risks[0].kind == "goodhart"
    assert back.metric_review.summary == "다중검정 주의"


def test_old_json_without_review_still_loads():
    # metric_review 없는 구(舊) json 도 None 으로 로드(하위호환)
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts())
    data = ctx.model_dump()
    data.pop("metric_review", None)
    import json
    back = DesignContext.from_json(json.dumps(data))
    assert back.metric_review is None


# ── 설계서 렌더 ───────────────────────────────────────────────────────
def test_doc_renders_risk_section():
    mr = MetricReview(risks=[MetricRisk(metric="클릭률", kind="goodhart", severity="high", note="전환 악화 가능")],
                      summary="총평")
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts(),
                                  metric_review=mr)
    doc = render_design_doc(ctx, mk_hyp())
    assert "지표 리스크 검토" in doc
    assert "Goodhart" in doc and "클릭률" in doc and "전환 악화 가능" in doc
    assert "총평" in doc


def test_doc_omits_section_when_no_review():
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts())
    doc = render_design_doc(ctx, mk_hyp())
    assert "지표 리스크 검토" not in doc


def test_doc_omits_section_when_empty_risks():
    mr = MetricReview(risks=[], summary="위험 없음")
    ctx = assemble_design_context(mk_hyp(), BiasScreenResult(biases=[], active_count=0), mk_facts(),
                                  metric_review=mr)
    doc = render_design_doc(ctx, mk_hyp())
    assert "지표 리스크 검토" not in doc
