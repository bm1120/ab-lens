"""Task D — 탭1/설계/Context Loop 공통 스키마 (v8).

DesignContext는 탭1→탭2 이월의 핵심 데이터다. 백엔드/세션DB 없이
ab-design-context.json 다운로드/업로드로 옮기므로, 직렬화 라운드트립과
스키마 버전 검증이 정확해야 한다.
"""
import json
import pytest

from src.design_schemas import DesignContext, DesignQuality, SCHEMA_VERSION


def make_context() -> DesignContext:
    return DesignContext(
        sharpened_hypothesis="결제 버튼을 상단으로 옮기면 체크아웃 전환율이 오른다",
        primary_metric="checkout_conversion",
        metric_type="proportion",
        agreed_mde=0.05,
        baseline=0.10,
        std_dev=None,
        alpha=0.05,
        power=0.8,
        target_sample_size=43000,
        experiment_duration_days=14,
        randomization_unit="user",
        icc=None,
        stop_criteria="목표 표본 43,000 도달 시 종료, 중간 peeking 금지",
        design_quality=DesignQuality(
            required_pass=True,
            required_items={"primary_metric_defined": True, "randomization_unit_clear": True},
            advisory_score=80,
            advisory_items={"hypothesis_sharpened": True, "mechanism_path_clear": True},
        ),
        bias_screening_summary="Confirmation Bias 경고: 선호 결과 지지 증거만 탐색 위험",
        alternative_selected=None,
    )


def test_to_json_from_json_roundtrip():
    ctx = make_context()
    restored = DesignContext.from_json(ctx.to_json())
    assert restored == ctx


def test_to_json_embeds_schema_version():
    data = json.loads(make_context().to_json())
    assert data["schema_version"] == SCHEMA_VERSION


def test_from_json_accepts_bytes():
    # st.file_uploader().read() 는 bytes 를 준다
    ctx = make_context()
    restored = DesignContext.from_json(ctx.to_json().encode("utf-8"))
    assert restored == ctx


def test_from_json_rejects_version_mismatch():
    data = json.loads(make_context().to_json())
    data["schema_version"] = "999.0"
    with pytest.raises(ValueError, match="schema version"):
        DesignContext.from_json(json.dumps(data))


def test_from_json_rejects_malformed():
    with pytest.raises(ValueError):
        DesignContext.from_json("{ not valid json")
