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
