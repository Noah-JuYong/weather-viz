# 🌤️ weather-viz

[Open-Meteo Archive API](https://open-meteo.com/) 로 서울의 일일 날씨를 매일 수집해
누적하고, 인터랙티브 차트로 시각화한 정적 리포트를 GitHub Pages로 배포하는 미니
데이터 파이프라인 프로젝트입니다. **API 키/가입이 전혀 필요 없습니다.**

```
Open-Meteo API → 수집(fetch) → 누적 저장(data/weather.csv) → pandas 분석
            → plotly 차트 + Jinja 템플릿 → index.html → GitHub Pages (매일 자동 갱신)
```

## 산출물

- **누적 데이터** `data/weather.csv` — 일별 최고/최저/평균 기온, 강수량, 최대 풍속
- **리포트** `index.html` — KPI 카드 + 기온 추이 / 강수량 / 월별 통계 / 극값(폭염·열대야·한파) 일수

## 구조

```
weather-viz/
├── fetch.py                  # Open-Meteo Archive API 수집 (키 불필요)
├── pipeline.py               # 누적 저장(upsert) + 분석 + HTML 렌더링 + CLI
├── template.html             # Jinja 리포트 템플릿
├── data/                     # weather.csv (자동 생성/커밋됨)
├── tests/test_pipeline.py    # 저장/분석 로직 검증 (네트워크 없음)
├── .github/workflows/daily.yml  # 매일 KST 09:00 실행 + 커밋
├── requirements.txt / requirements-dev.txt
└── pyproject.toml            # pytest pythonpath 설정
```

## 로컬 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # 테스트까지

# 최근 1년 갱신 (기본값). 키/가입 불필요
python pipeline.py

# 기간/구간 조정
python pipeline.py --days 90
python pipeline.py --backfill 2025-01-01 2025-12-31

# 테스트
pytest
```

> 다른 지역으로 바꾸려면 `fetch.py` 의 `SEOUL_LAT`/`SEOUL_LON` 상수를 편집하세요.

## GitHub 배포 (최초 1회)

이 프로젝트는 비밀키가 필요 없어 바로 배포됩니다.

1. **Settings → Pages** → Source: `Deploy from a branch` / Branch: `main` / Folder: `/ (root)`
2. **Actions 탭**에서 `Daily weather update` 를 `Run workflow` 로 수동 1회 실행
   → 이후 매일 KST 09:00 자동 갱신

배포 주소: `https://<계정>.github.io/weather-viz/`

## 데이터 출처

[Open-Meteo](https://open-meteo.com/) (서울 위도 37.5665, 경도 126.9780, timezone Asia/Seoul)
