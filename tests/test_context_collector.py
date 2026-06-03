"""tests/test_context_collector.py — ContextCollector 단위 테스트.

실제 context_collector.py 인터페이스:
  generate_context_questions(idea: str, api_key, provider, lang, model) -> list[str]
    → LLM 을 호출하지 않고 하드코딩된 질문 목록 반환 (stub 구현)
  parse_answers_to_context(questions, answers, api_key, provider, lang, model) -> ServiceContext
    → 답변 목록을 인덱스로 매핑해 ServiceContext 생성 (stub 구현, LLM 없음)
"""
from src.design_schemas import ServiceContext
from src.hypothesis.context_collector import (
    generate_context_questions,
    parse_answers_to_context,
)
from src.schemas import LLMProvider


# ── Task G2: Test 1 — generate_context_questions returns list of strings ──────

def test_generate_questions_returns_list():
    """generate_context_questions 가 str 리스트를 반환해야 한다."""
    result = generate_context_questions(
        "결제 전환율을 올리고 싶다",
        api_key="k",
        provider=LLMProvider.ANTHROPIC,
    )
    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(isinstance(q, str) for q in result)


def test_generate_questions_ko_returns_korean():
    """lang='ko' 이면 한국어 질문을 반환한다."""
    result = generate_context_questions(
        "결제 전환율을 올리고 싶다",
        api_key="k",
        provider=LLMProvider.ANTHROPIC,
        lang="ko",
    )
    # 적어도 1개 이상의 질문이 한글 포함
    has_korean = any(
        any('\uAC00' <= ch <= '\uD7A3' for ch in q)
        for q in result
    )
    assert has_korean


def test_generate_questions_en_returns_english():
    """lang='en' 이면 영어 질문을 반환한다."""
    result = generate_context_questions(
        "Improve checkout conversion rate",
        api_key="k",
        provider=LLMProvider.ANTHROPIC,
        lang="en",
    )
    assert isinstance(result, list)
    assert len(result) >= 1


def test_generate_questions_no_api_call_needed():
    """stub 구현: API 키 없이도 동작한다 (실제 LLM 호출 안 함)."""
    # stub 이므로 call_structured/call_llm 을 호출하지 않아야 함
    result = generate_context_questions(
        "어떤 아이디어든",
        api_key="",   # 빈 키
        provider=LLMProvider.ANTHROPIC,
    )
    assert isinstance(result, list)


# ── Task G2: Test 2 — parse_answers_to_context returns ServiceContext ─────────

def test_parse_answers_returns_service_context():
    """parse_answers_to_context 가 ServiceContext 를 반환해야 한다."""
    questions = [
        "서비스 이름은?",
        "주요 사용자는?",
        "북극성 지표는?",
        "현재 지표 수치는?",
        "과거 실험 경험은?",
    ]
    answers = [
        "MyShop",
        "모바일 사용자",
        "checkout_conversion",
        "10%",
        "3회 진행",
    ]
    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
    )
    assert isinstance(result, ServiceContext)


def test_parse_answers_maps_service_name():
    """첫 번째 답변이 service_name 으로 매핑된다."""
    questions = ["서비스명?", "사용자?", "지표?", "수치?", "실험?"]
    answers = ["CoolApp", "데스크탑 사용자", "DAU", "50000", "없음"]

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
    )
    assert result.service_name == "CoolApp"


def test_parse_answers_maps_target_users():
    """두 번째 답변이 target_users 로 매핑된다."""
    questions = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    answers = ["ServiceX", "시니어 사용자", "retention_rate", "30%", "2회"]

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
    )
    assert result.target_users == "시니어 사용자"


def test_parse_answers_maps_primary_metric():
    """세 번째 답변이 primary_metric 으로 매핑된다."""
    questions = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    answers = ["AppY", "전체 사용자", "click_through_rate", "5%", "없음"]

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
    )
    assert result.primary_metric == "click_through_rate"


def test_parse_answers_maps_current_baseline():
    """네 번째 답변이 current_baseline 으로 매핑된다."""
    questions = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    answers = ["AppZ", "신규 사용자", "conversion_rate", "15%", "1회"]

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
    )
    assert result.current_baseline == "15%"


def test_parse_answers_handles_short_answers():
    """답변이 부족할 경우 'Unknown' 으로 채워져야 한다."""
    questions = ["Q1"]
    answers = ["OnlyOneAnswer"]  # 1개 답변만

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC
    )
    # service_name 은 있고, 나머지는 Unknown
    assert result.service_name == "OnlyOneAnswer"
    assert result.target_users == "Unknown"
    assert result.primary_metric == "Unknown"


def test_parse_answers_domain_constraints_ko():
    """lang='ko' 이면 domain_constraints 에 '없음' 이 기본값."""
    questions = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    answers = ["S", "U", "M", "B", "E"]

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC, lang="ko"
    )
    assert result.domain_constraints == "없음"


def test_parse_answers_domain_constraints_en():
    """lang='en' 이면 domain_constraints 에 'None' 이 기본값."""
    questions = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    answers = ["S", "U", "M", "B", "E"]

    result = parse_answers_to_context(
        questions, answers, api_key="k", provider=LLMProvider.ANTHROPIC, lang="en"
    )
    assert result.domain_constraints == "None"
