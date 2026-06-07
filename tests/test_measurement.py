"""조작적 정의화 — 개념적 정의 + 측정지표 후보(탭2 호환 강제)."""
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.hypothesis.measurement import (
    ConstructMeasurement,
    MeasurementProposal,
    MetricCandidate,
    PinnedMetrics,
    propose_measurement,
)
from src.schemas import LLMProvider


def test_metric_candidate_allows_tab2_types():
    for t in ("proportion", "continuous", "count"):
        assert MetricCandidate(label="x", metric_type=t, rationale="r").metric_type == t


def test_metric_candidate_rejects_incompatible_type():
    # 탭2 통계엔진은 proportion/continuous/count 만 → 'survey' 등은 스키마에서 거부
    with pytest.raises(ValidationError):
        MetricCandidate(label="설문 회상률", metric_type="survey", rationale="r")


def test_ab_testable_defaults_true():
    assert MetricCandidate(label="x", metric_type="count", rationale="r").ab_testable is True


def test_propose_measurement_passes_schema():
    fake = MeasurementProposal(measurements=[
        ConstructMeasurement(construct_name="브랜드 인지도",
                             conceptual_definition="비보조 회상 정도",
                             candidates=[MetricCandidate(label="브랜드 검색량", metric_type="count", rationale="대리")])
    ])
    with patch("src.hypothesis.measurement.call_structured", return_value=fake) as m:
        out = propose_measurement("아이디어", ["브랜드 인지도"], api_key="k", provider=LLMProvider.CLAUDE_CODE)
    assert out.measurements[0].construct_name == "브랜드 인지도"
    assert m.call_args.kwargs["schema"] is MeasurementProposal


def test_pinned_metrics_shape():
    p = PinnedMetrics(primary_metric="전환율", secondary_metrics=["체류시간"])
    assert p.primary_metric == "전환율"
    assert p.secondary_metrics == ["체류시간"]


# ── P1 리뷰 반영 (Gemini/Codex) ──────────────────────────────────────────

def test_measurement_exception_falls_back_gracefully():
    # 생성 실패 시 크래시 대신 구조적 폴백(needs_question=True)으로 복구 (리뷰 B)
    with patch("src.hypothesis.measurement.call_structured", side_effect=RuntimeError("api down")):
        out = propose_measurement("아이디어", ["신뢰"], api_key="k", provider=LLMProvider.CLAUDE_CODE)
    assert out.measurements == []
    assert out.needs_question is True
    assert out.question


def test_incompatible_signal_forces_ab_testable_false():
    # label/rationale에 설문·회상 같은 비호환 신호 → ab_testable 강제 False (리뷰 A)
    fake = MeasurementProposal(measurements=[
        ConstructMeasurement(construct_name="브랜드 인지도", conceptual_definition="회상 정도",
            candidates=[MetricCandidate(label="설문 회상률", metric_type="proportion",
                                        ab_testable=True, rationale="설문으로 측정")])
    ])
    with patch("src.hypothesis.measurement.call_structured", return_value=fake):
        out = propose_measurement("아이디어", ["브랜드 인지도"], domain_context="이커머스",
                                  api_key="k", provider=LLMProvider.CLAUDE_CODE)
    assert out.measurements[0].candidates[0].ab_testable is False


def test_empty_domain_context_forces_needs_question():
    # 도메인 맥락 비면 needs_question 보정 (리뷰 C)
    fake = MeasurementProposal(measurements=[
        ConstructMeasurement(construct_name="만족도", conceptual_definition="x",
            candidates=[MetricCandidate(label="재방문율", metric_type="proportion", rationale="r")])
    ], needs_question=False)
    with patch("src.hypothesis.measurement.call_structured", return_value=fake):
        out = propose_measurement("아이디어", ["만족도"], domain_context="",
                                  api_key="k", provider=LLMProvider.CLAUDE_CODE)
    assert out.needs_question is True


def test_proxy_warning_field_exists():
    cm = ConstructMeasurement(construct_name="신뢰", conceptual_definition="x",
                              candidates=[], proxy_warning="단기 행동지표는 장기 신뢰의 대리일 뿐")
    assert "대리" in cm.proxy_warning


# ── diverse 이월 가드레일: 설계 확정 시 측정 타당도 soft 경고 판정 (순수) ──

def test_warning_when_abstract_and_unconfirmed():
    # diverse/skip 경로: 추상인데 측정확인 미경유 → 경고
    from src.hypothesis.measurement import needs_measurement_warning
    assert needs_measurement_warning(construct_kind="abstract", measurement_confirmed=False) is True
    assert needs_measurement_warning(construct_kind="mixed", measurement_confirmed=False) is True


def test_no_warning_when_confirmed():
    # 측정확인 경유(pinned) → 추상이어도 경고 없음 (이미 타당도 확인됨)
    from src.hypothesis.measurement import needs_measurement_warning
    assert needs_measurement_warning(construct_kind="abstract", measurement_confirmed=True) is False
    assert needs_measurement_warning(construct_kind="mixed", measurement_confirmed=True) is False


def test_no_warning_when_clear():
    # 명확 구성개념 → 측정확인 불필요, 미경유여도 경고 없음
    from src.hypothesis.measurement import needs_measurement_warning
    assert needs_measurement_warning(construct_kind="clear", measurement_confirmed=False) is False
    assert needs_measurement_warning(construct_kind="clear", measurement_confirmed=True) is False
