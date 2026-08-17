# weather-viz 폴더 구조 정리 설계

## 배경

현재 저장소 루트에는 Python 소스, Jinja 템플릿, GitHub Pages 배포 결과물, 데이터, 설정 파일이 함께 있다. 파일 수는 많지 않지만 소스와 생성물이 같은 위치에 있어 각 파일의 성격을 한눈에 구분하기 어렵다.

이번 작업은 기능을 바꾸거나 `pipeline.py` 내부 책임을 재설계하는 리팩터링이 아니다. 먼저 폴더 역할을 명확히 나누고, 이후 모듈 분리가 필요할 때 안전하게 진행할 수 있는 기반을 만든다.

## 검토한 방식

### 1. `src/` 패키지 구조 — 선택

Python 코드를 `src/weather_viz/`에 두고 템플릿을 패키지 하위에 둔다. 소스, 테스트, 생성물을 명확히 분리할 수 있고 Python 프로젝트의 일반적인 구조와도 맞는다. 대신 로컬 및 CI에서 패키지를 editable 모드로 설치하는 설정이 필요하다.

### 2. 루트 패키지 구조

`weather_viz/`를 저장소 루트에 바로 둔다. 실행 설정은 단순하지만 소스 패키지와 배포 결과물이 여전히 같은 최상위 계층에 놓인다.

### 3. `scripts/`로 기존 파일만 이동

`fetch.py`와 `pipeline.py`를 `scripts/`에 넣는 가장 작은 변경이다. 단순 실행 파일 모음처럼 보여 패키지의 책임과 테스트 대상이 명확하지 않고, 장기적인 모듈 분리 기반으로는 약하다.

## 선택한 구조

```text
weather-viz/
├── .github/workflows/daily.yml
├── src/weather_viz/
│   ├── __init__.py
│   ├── __main__.py
│   ├── fetch.py
│   ├── pipeline.py
│   └── templates/
│       └── report.html
├── tests/
│   ├── test_fetch.py
│   └── test_pipeline.py
├── data/
│   ├── seoul.csv
│   ├── busan.csv
│   └── jeju.csv
├── index.html
├── busan.html
├── jeju.html
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── LICENSE
└── .nojekyll
```

## 파일 역할

- `src/weather_viz/fetch.py`: Open-Meteo 요청과 재시도 정책을 담당한다.
- `src/weather_viz/pipeline.py`: 누적 저장, 분석, 차트 구성, 렌더링 흐름을 유지한다.
- `src/weather_viz/templates/report.html`: 도시별 페이지를 만드는 Jinja 템플릿이다.
- `src/weather_viz/__main__.py`: `python -m weather_viz` 실행 진입점이다.
- `tests/`: 설치된 `weather_viz` 패키지의 공개 경로를 통해 동작을 검증한다.
- 루트 HTML과 `data/`: GitHub Pages가 루트에서 바로 제공하고 Actions가 갱신하는 생성물이다.

## 경로와 실행 방식

`pipeline.py`는 패키지 디렉터리가 아니라 저장소 루트를 기준으로 `data/`와 HTML 출력 경로를 계산해야 한다. 템플릿 경로만 패키지 내부 `templates/report.html`을 사용한다.

로컬 실행과 Actions 실행은 다음으로 통일한다.

```bash
python -m weather_viz --days 365
```

이를 위해 `pyproject.toml`에 최소 패키지 메타데이터와 `src` 패키지 검색 설정을 추가한다. 의존성 관리는 기존 `requirements*.txt`를 유지하고, 패키지는 `pip install --no-deps -e .`로 설치한다.

## 유지해야 할 동작

- 일반 실행은 마지막 관측일 다음 날부터 누락분만 수집한다.
- `--backfill START END`는 지정 기간 전체를 다시 수집한다.
- 서울은 `index.html`, 부산과 제주는 각 도시명 HTML로 렌더링한다.
- CSV와 HTML은 계속 저장소 루트의 기존 위치에 생성한다.
- GitHub Pages 설정은 `main` 브랜치의 `/root`를 그대로 사용한다.
- 일일 Actions 실행은 데이터와 HTML 변경분을 계속 자동 커밋한다.

## 오류 처리

폴더 이동 후에도 Open-Meteo 타임아웃·연결 오류 재시도와 `FetchError` 동작을 유지한다. 저장소 루트나 템플릿을 찾지 못하면 잘못된 위치에 파일을 생성하지 않고 즉시 실패해야 한다.

## 검증

1. 전체 pytest 테스트가 새 패키지 import 경로에서 통과한다.
2. 임시 복사본에서 `python -m weather_viz --days 365`를 실행한다.
3. `index.html`, `busan.html`, `jeju.html`, `data/*.csv`가 루트에 생성되는지 확인한다.
4. `git diff --check`로 이동 및 설정 변경에 형식 오류가 없는지 확인한다.
5. PR 머지 후 `Daily weather update`를 수동 실행해 Actions 환경에서 검증한다.

## 제외 범위

- `pipeline.py`를 저장·분석·차트 모듈로 추가 분리하는 작업
- 생성 HTML을 `docs/` 또는 별도 배포 브랜치로 옮기는 작업
- 차트 UI나 데이터 스키마 변경
- 의존성 관리 도구 교체
