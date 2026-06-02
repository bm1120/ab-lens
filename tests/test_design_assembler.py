"""DesignContext 조립 + 설계서 MD 생성 (deterministic, LLM 없음).

가설 고도화 결과(HypothesisOutput) + 사용자 사실수치 → DesignContext.
LLM 은 수치를 만들지 않는다(불변 원칙): target_sample_size 는 calculate_sample_size 로 계산.
"""
from src.design.assembler import DesignFacts, assemble_design_context
from src.design.doc_generator import render_design_doc
from src.design_schemas import DesignContext, HypothesisOutput
from src.design_stats import calculate_sample_size
from tests.test_sharpener import _hypothesis
from src.design_schemas import BiasScreenItem, BiasScreenResult


def _facts():
    return DesignFacts(
        metric_type="proportion",
        baseline=0.10,
        agreed_mde=0.05,
        std_dev=None,
        alpha=0.05,
        power=0.8,
        randomization_unit="user",
        experiment_duration_days=14,
        icc=None,
        stop_criteria="목표 표본 도달 시 종료",
    )


def _bias():
    return BiasScreenResult(
        biases=[BiasScreenItem(bias_type="confirmation_bias", status="active",
                               evidence="e", counter_measure="c")],
        active_count=1,
    )


def test_assemble_uses_hypothesis_primary_metric():
    ctx = assemble_design_context(_hypothesis(), _bias(), _facts())
    assert isinstance(ctx, DesignContext)
    assert ctx.primary_metric == "checkout_conversion"


def test_assemble_sample_size_matches_calculator():
    facts = _facts()
    ctx = assemble_design_context(_hypothesis(), _bias(), facts)
    expected = calculate_sample_size(
        metric_type="proportion", baseline=0.10, mde=0.05, alpha=0.05, power=0.8
    ).total
    assert ctx.target_sample_size == expected


def test_assemble_summarizes_active_bias():
    ctx = assemble_design_context(_hypothesis(), _bias(), _facts())
    assert "confirmation_bias" in ctx.bias_screening_summary


def test_assemble_roundtrips_to_json():
    ctx = assemble_design_context(_hypothesis(), _bias(), _facts())
    assert DesignContext.from_json(ctx.to_json()) == ctx


def test_design_doc_contains_key_sections():
    ctx = assemble_design_context(_hypothesis(), _bias(), _facts())
    md = render_design_doc(ctx, _hypothesis())
    assert "# " in md                                   # 제목
    assert ctx.sharpened_hypothesis in md
    assert f"{ctx.target_sample_size:,}" in md          # 샘플사이즈 인용 (콤마 포맷)
    assert "checkout_conversion" in md                  # 1차 지표
    assert "기각" in md or "Rejected" in md             # 기각 대안 로그


def test_design_doc_does_not_invent_numbers():
    # 설계서에 등장하는 수치는 ctx 의 값이어야 한다 (LLM 생성 금지)
    ctx = assemble_design_context(_hypothesis(), _bias(), _facts())
    md = render_design_doc(ctx, _hypothesis())
    assert f"{ctx.agreed_mde}" in md
    assert f"{ctx.baseline}" in md
