# 🌤️ weather-viz

![CI](https://github.com/Noah-JuYong/weather-viz/actions/workflows/daily.yml/badge.svg)
![Pages](https://img.shields.io/badge/GitHub%20Pages-live-0ea5e9)
![Python](https://img.shields.io/badge/python-3.11+-3776ab)
![License](https://img.shields.io/badge/license-MIT-green)

[Open-Meteo](https://open-meteo.com/)의 서울·부산·제주 일일 날씨를 수집해 도시별 CSV에
누적하고, 인터랙티브 정적 리포트로 보여 주는 작은 데이터 파이프라인입니다. API 키나
가입은 필요하지 않습니다.

라이브 리포트: <https://noah-juyong.github.io/weather-viz/>

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m weather_viz
pytest
```

실행하면 Open-Meteo에서 새 데이터를 가져와 `data/`의 도시별 CSV를 갱신하고, 리포트를
`site/`에 생성합니다. 수집 과정은 기존 데이터를 재사용하는 증분 방식이므로 매번 전체
기간을 다시 요청하지 않습니다.

## 공개 구조

```
weather-viz/
├── .github/                 # 데이터 갱신과 Pages 배포 자동화
├── data/                    # Git으로 추적하는 도시별 누적 CSV
├── docs/architecture.md     # 데이터 흐름과 저장소 경계
├── src/weather_viz/         # 수집과 리포트 생성 코드
├── tests/                   # 네트워크 없이 실행되는 회귀 테스트
└── pyproject.toml           # 패키지와 개발 의존성
```

생성된 HTML은 Git에 저장하지 않습니다. GitHub Actions가 실행 중 `site/`에 HTML을 만들고,
이를 GitHub Pages 아티팩트로 배포합니다. 따라서 저장소에는 재생성 가능한 소스와 누적
데이터만 남습니다.

[상세 구조](docs/architecture.md)에서 데이터 흐름, 단계별 실패 처리, 자동 배포 방식을
확인할 수 있습니다.

## 데이터 출처

[Open-Meteo](https://open-meteo.com/) (Archive API: 과거 관측 / Forecast API: 단기 예보,
timezone Asia/Seoul)
