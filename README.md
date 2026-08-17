# 🌤️ weather-viz

![CI](https://github.com/Noah-JuYong/weather-viz/actions/workflows/daily.yml/badge.svg)
![Pages](https://img.shields.io/badge/GitHub%20Pages-live-0ea5e9)
![Python](https://img.shields.io/badge/python-3.11+-3776ab)
![License](https://img.shields.io/badge/license-MIT-green)

[Open-Meteo](https://open-meteo.com/) 로 **서울·부산·제주** 일일 날씨(과거 관측 + 향후 7일 예보)를
매일 수집·누적하고, 인터랙티브 차트로 시각화한 정적 리포트를 GitHub Pages로 배포하는
미니 데이터 파이프라인입니다. **API 키/가입이 전혀 필요 없습니다.**

🔗 **라이브**: <https://noah-juyong.github.io/weather-viz/>

```
Open-Meteo API → 수집(fetch) → 도시별 누적(data/<slug>.csv) → pandas 분석
            → plotly 차트 + Jinja 템플릿 → 도시별 페이지 → GitHub Pages (매일 자동 갱신)
```

## 차트

- **기온 추이** — 관측 최고/최저 밴드 + 평균 7일 이동평균 + 향후 예보(점선) + 폭염/한파 기준선
- **일일 강수량** / **월별 통계** / **극값 일수**(폭염·열대야·한파)
- **향후 7일 예보** — 최고·최저 기온 + 강수량
- 상단 탭으로 **서울 / 부산 / 제주** 전환

## 구조

```
weather-viz/
├── src/weather_viz/          # 애플리케이션 패키지
│   ├── __main__.py           # `python -m weather_viz` 실행 진입점
│   ├── fetch.py              # Open-Meteo 관측·예보 수집
│   ├── pipeline.py           # 누적 저장·분석·렌더링·CLI
│   └── templates/report.html # Jinja 리포트 템플릿
├── tests/                    # 수집·파이프라인·CLI 테스트 (네트워크 없음)
├── data/                     # 도시별 누적 CSV (자동 생성·커밋)
├── index.html                # 서울 페이지 (GitHub Pages 진입점)
├── busan.html / jeju.html    # 부산·제주 페이지
├── .github/workflows/daily.yml  # 매일 KST 09:00 실행 + 커밋
├── requirements.txt / requirements-dev.txt
├── pyproject.toml            # 패키징·pytest 설정
└── LICENSE                   # MIT
```

Python 코드와 템플릿은 `src/weather_viz/`에 모았습니다. 반면 `data/`와 도시별 HTML은
GitHub Pages가 별도 빌드 설정 없이 바로 배포할 수 있도록 저장소 루트에 유지합니다.

## 로컬 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # 런타임 + 테스트 의존성
pip install --no-deps -e .            # weather_viz 패키지 연결

python -m weather_viz                 # 모든 도시, 최근 1년 갱신 (키/가입 불필요)
python -m weather_viz --days 90
python -m weather_viz --backfill 2025-01-01 2025-12-31
pytest
```

> 도시를 추가하거나 변경하려면 `src/weather_viz/pipeline.py`의 `CITIES` 목록을 편집하세요.

## 자동 배포

이 프로젝트는 비밀키가 필요 없습니다. `main` 에 푸시하면:
1. **Pages**(Settings → Pages → `main` / `/root`)가 이미 활성화되어 있음
2. 매일 **KST 09:00** GitHub Actions 가 실행되어 도시별 페이지와 데이터를 갱신·배포

## 데이터 출처

[Open-Meteo](https://open-meteo.com/) (Archive API: 과거 관측 / Forecast API: 단기 예보, timezone Asia/Seoul)
