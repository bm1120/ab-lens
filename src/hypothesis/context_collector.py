"""서비스 컨텍스트 수집 모듈 (stub — backend agent가 구현 예정).

이 파일은 UI 연동을 위한 인터페이스 stub 입니다.
실제 구현은 feat/hypothesis-refinement-loop 브랜치의 backend agent가 담당합니다.
"""
from __future__ import annotations

from src.design_schemas import ServiceContext
from src.schemas import LLMProvider


def generate_context_questions(
    idea: str,
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> list[str]:
    """아이디어에 맞는 서비스 컨텍스트 질문 생성 (stub)."""
    if lang == "ko":
        return [
            "서비스/제품 이름이 뭔가요?",
            "주요 사용자 세그먼트는 누구인가요?",
            "북극성 지표는 무엇인가요?",
            "현재 그 지표의 대략적인 수치는?",
            "과거에 유사한 실험을 진행한 적 있나요?",
        ]
    return [
        "What is the name of your service/product?",
        "Who are your primary user segments?",
        "What is your north-star metric?",
        "What is the approximate current value of that metric?",
        "Have you run similar experiments before?",
    ]


def parse_answers_to_context(
    questions: list[str],
    answers: list[str],
    api_key: str,
    provider: LLMProvider,
    lang: str = "ko",
    model: str | None = None,
) -> ServiceContext:
    """질문/답변 쌍으로 ServiceContext 생성 (stub)."""
    return ServiceContext(
        service_name=answers[0] if len(answers) > 0 else "Unknown",
        target_users=answers[1] if len(answers) > 1 else "Unknown",
        primary_metric=answers[2] if len(answers) > 2 else "Unknown",
        current_baseline=answers[3] if len(answers) > 3 else "Unknown",
        past_experiments=answers[4] if len(answers) > 4 else "None",
        domain_constraints="없음" if lang == "ko" else "None",
    )
