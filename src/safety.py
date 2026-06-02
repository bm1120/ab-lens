import streamlit as st


class SessionLimiter:
    MAX_REQUESTS = 10
    MAX_INPUT_CHARS = 3000

    def __init__(self):
        if "request_count" not in st.session_state:
            st.session_state.request_count = 0

    def check_and_increment(self) -> bool:
        """
        요청 카운터를 확인하고 증가시킵니다.
        제한 초과 시 False 반환, 정상 시 True 반환.
        """
        if st.session_state.request_count >= self.MAX_REQUESTS:
            return False
        st.session_state.request_count += 1
        return True

    def validate_input(self, text: str) -> str:
        """
        입력 텍스트 길이를 제한합니다.
        MAX_INPUT_CHARS를 초과하면 잘라서 반환합니다.
        """
        if text and len(text) > self.MAX_INPUT_CHARS:
            return text[: self.MAX_INPUT_CHARS]
        return text

    @property
    def remaining_requests(self) -> int:
        """남은 요청 횟수를 반환합니다."""
        return max(0, self.MAX_REQUESTS - st.session_state.get("request_count", 0))

    def reset(self):
        """요청 카운터를 초기화합니다."""
        st.session_state.request_count = 0
