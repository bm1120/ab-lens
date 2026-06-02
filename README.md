# 🔬 AB Lens

A/B 테스트 결과를 입력하면 AI가 통계 해석·편향 감지·인과추론 대안을 1페이지로 정리합니다.

![demo](demo/demo.gif)

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.35+-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

AB Lens는 A/B 테스트 결과 해석을 돕는 AI 기반 1페이지 브리핑 도구입니다.  
실험 담당자가 통계 해석, 인지 편향 감지, 인과추론 대안 탐색을 빠르게 수행할 수 있도록 설계되었습니다.

**핵심 파이프라인:**
```
사용자 입력 → 통계 분석 → 편향 감지 (LLM) → 추천 생성 (LLM) → 1페이지 브리핑
```

---

## Features

- 📊 **통계 분석**: Two-proportion z-test, 검정력(Power) 분석, SRM 감지
- ⚠️ **편향 감지**: Confirmation Bias, Sunk Cost Fallacy, Anchoring Bias, p-hacking/HARKing, Novelty Effect 5가지 자동 감지
- 🔗 **인과추론**: 무작위 배정이 없는 경우 대안적 인과추론 방법 제안
- 💡 **의사결정 지원**: 출시/추가실험/조건부출시 3개 시나리오 + 최종 추천
- 🌐 **이중언어**: 한국어/English 토글 지원
- 🔒 **Safety Layer**: 세션당 요청 제한 (10회) + 입력 길이 제한 (3000자)
- ⚡ **Prompt Caching**: Anthropic API 비용 최적화

---

## Quick Start

### 1. 환경 설치

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 프로젝트 클론
git clone https://github.com/yourname/ab-lens.git
cd ab-lens

# 의존성 설치
uv sync
```

### 2. 앱 실행

```bash
uv run streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

### 3. API 키 설정

- 사이드바에서 Anthropic API 키 입력 (`sk-ant-...`)
- [Anthropic Console](https://console.anthropic.com/)에서 발급

---

## Architecture

```
ab-lens/
├── app.py                  # Streamlit 메인 앱
├── src/
│   ├── schemas.py          # Pydantic v2 데이터 모델
│   ├── safety.py           # 요청 제한 Safety Layer
│   ├── agents/
│   │   ├── statistical.py  # 통계 분석 (scipy, statsmodels)
│   │   ├── bias_detector.py # 편향 감지 (Anthropic API)
│   │   └── recommender.py  # 추천 생성 (Anthropic API)
│   ├── prompts/
│   │   ├── bias_check.py   # 편향 감지 System Prompt
│   │   └── recommender.py  # 추천 System Prompt
│   └── i18n/
│       ├── ko.py           # 한국어 텍스트
│       └── en.py           # English texts
├── tests/
│   ├── test_statistical.py # 통계 함수 단위 테스트
│   ├── test_bias_detector.py # 편향 감지 테스트 (mock)
│   └── scenarios/          # 테스트 시나리오 JSON
└── demo/
    └── scenarios.py        # 데모 시나리오 객체
```

**실행 흐름:**
1. `analyze_stats()` — scipy 기반 순수 통계 계산 (API 없음)
2. `detect_bias()` — Claude API 호출, Prompt Caching 적용
3. `recommend()` — Claude API 호출, Prompt Caching 적용

---

## Tech Stack

| 구분 | 기술 |
|------|------|
| Language | Python 3.11 |
| Package Manager | uv |
| Web Framework | Streamlit >= 1.35 |
| AI SDK | Anthropic >= 0.30 |
| Data Validation | Pydantic v2 |
| Statistics | scipy >= 1.11, statsmodels |
| Testing | pytest >= 8.0, pytest-mock |

---

## Running Tests

```bash
# 전체 테스트 실행
uv run pytest

# 상세 출력
uv run pytest -v

# 특정 테스트만
uv run pytest tests/test_statistical.py -v
```

테스트는 Anthropic API를 호출하지 않으므로 API 키 없이 실행 가능합니다.

---

## Streamlit Cloud 배포

1. GitHub에 레포지토리 푸시
2. [Streamlit Cloud](https://streamlit.io/cloud)에서 배포
3. Secrets 설정: `ANTHROPIC_API_KEY` (선택 - 사용자가 직접 입력 가능)

```toml
# .streamlit/secrets.toml (선택)
ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

*Built with ❤️ using Streamlit + Anthropic Claude*
