"""i18n 패키지 초기화"""

from src.i18n.ko import TEXTS as KO_TEXTS
from src.i18n.en import TEXTS as EN_TEXTS


def get_texts(lang: str = "ko") -> dict:
    """언어 코드에 맞는 텍스트 딕셔너리를 반환합니다."""
    if lang == "en":
        return EN_TEXTS
    return KO_TEXTS
