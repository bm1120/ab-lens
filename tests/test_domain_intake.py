"""T2 도메인 인테이크 테스트 — analyze_domain(mock) / context_from_answers / to_prompt / 폴백."""
from src.hypothesis.domain_intake import (
    DomainContext, DomainQuestion, DomainIntake,
    analyze_domain, context_from_answers,
)


def test_to_prompt_only_filled_fields():
    ctx = DomainContext(service_type="커머스", primary_goal="전환율")
    p = ctx.to_prompt("ko")
    assert "커머스" in p and "전환율" in p
    assert "타겟 사용자" not in p           # 빈 필드는 생략
    assert DomainContext().to_prompt("ko") == ""   # 전부 비면 빈 문자열


def test_context_from_answers_maps_fields():
    qs = [DomainQuestion(field="service_type", question="?"),
          DomainQuestion(field="user_segment", question="?"),
          DomainQuestion(field="other", question="?")]
    ctx = context_from_answers(qs, {"service_type": "SaaS", "user_segment": "B2B 관리자", "other": "GDPR 규제"})
    assert ctx.service_type == "SaaS" and ctx.user_segment == "B2B 관리자"
    assert "GDPR" in ctx.constraints          # other → constraints


def test_context_from_answers_skips_blank_and_keeps_base():
    base = DomainContext(primary_goal="리텐션")
    ctx = context_from_answers([DomainQuestion(field="service_type", question="?")],
                               {"service_type": ""}, base=base)
    assert ctx.primary_goal == "리텐션" and ctx.service_type == ""   # 빈 답 무시, base 유지


def test_analyze_domain_sufficient(monkeypatch):
    fake = DomainIntake(sufficient=True, inferred=DomainContext(service_type="커머스"), questions=[])
    intake = analyze_domain("결제 버튼 옮기기", api_key="k", provider=None,
                            _call=lambda **kw: fake)
    assert intake.sufficient is True and not intake.questions


def test_analyze_domain_insufficient_returns_questions():
    fake = DomainIntake(sufficient=False, inferred=DomainContext(),
                        questions=[DomainQuestion(field="user_segment", question="타겟 사용자는?"),
                                   DomainQuestion(field="primary_goal", question="핵심 지표는?")])
    intake = analyze_domain("뭔가 좋게", api_key="k", provider=None, _call=lambda **kw: fake)
    assert intake.sufficient is False
    assert len(intake.questions) == 2
    assert intake.questions[0].field == "user_segment"


def test_analyze_domain_exception_falls_back_to_sufficient():
    def boom(**kw):
        raise RuntimeError("api down")
    intake = analyze_domain("idea", DomainContext(service_type="x"), api_key="k", provider=None, _call=boom)
    assert intake.sufficient is True and intake.questions == []   # 실패 시 진행(고도화 막지 않음)
