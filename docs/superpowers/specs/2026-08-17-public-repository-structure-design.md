# 공개 저장소 구조 개선 설계

## 배경

현재 `weather-viz`는 Python 소스와 테스트를 `src/`, `tests/`로 분리했지만, GitHub Pages가 `main` 브랜치의 루트를 직접 제공하기 때문에 생성된 `index.html`, `busan.html`, `jeju.html`이 저장소 최상위에 남아 있다. 또한 런타임 의존성은 `requirements.txt`, 개발 의존성은 `requirements-dev.txt`, 패키징 정보는 `pyproject.toml`에 나뉘어 있다. `docs/superpowers/`에는 완료된 작업의 내부 설계와 실행 계획이 있어 외부 방문자에게 필요한 문서와 작업 기록의 성격도 섞여 있다.

이번 변경의 목표는 처음 방문한 사람이 폴더명과 README만으로 코드, 테스트, 공개 데이터, 문서의 역할을 구분할 수 있게 만드는 것이다. 웹페이지와 누적 데이터의 기존 기능 및 공개 URL은 유지한다.

## 결정

### 1. GitHub Pages는 Actions 아티팩트로 배포한다

생성된 HTML은 더 이상 `main`에 커밋하지 않는다. 파이프라인은 저장소 루트의 `site/`에 다음 파일을 생성한다.

```text
site/
├── .nojekyll
├── index.html
├── busan.html
└── jeju.html
```

`site/`는 `.gitignore`에 포함한다. GitHub Actions는 `site/`를 Pages 아티팩트로 업로드하고 공식 Pages 배포 작업으로 게시한다. 기존 공개 URL인 `https://noah-juyong.github.io/weather-viz/`는 유지한다.

GitHub 저장소의 Pages 빌드 방식은 `main / root`에서 `GitHub Actions`로 전환한다. 전환 설정을 준비한 뒤 이번 구조 변경에서 루트의 `.nojekyll`과 도시별 HTML을 함께 제거한다. 병합 직후 새 워크플로를 수동 실행하고, 성공한 Pages 배포와 기존 공개 URL을 확인한다.

### 2. 누적 CSV는 공개 데이터로 `main`에 유지한다

`data/seoul.csv`, `data/busan.csv`, `data/jeju.csv`는 다음 실행의 증분 수집 기준이자 공개 데이터이므로 계속 추적한다. 일일 워크플로의 자동 커밋 범위는 `data/*.csv`로 제한한다. `git add -A`를 사용하지 않아 생성물이나 우연한 파일이 자동 커밋되는 일을 막는다.

파이프라인 실행 순서는 다음과 같다.

```text
Open-Meteo 수집
  → data/*.csv 증분 갱신
  → site/*.html 렌더링
  → data/*.csv만 main에 커밋
  → site/를 Pages 아티팩트로 배포
```

수집 또는 렌더링이 실패하면 이후 커밋과 배포 단계는 실행하지 않는다.

### 3. 공개 저장소의 최종 구조

```text
weather-viz/
├── .github/
│   └── workflows/
│       └── daily.yml
├── data/
│   ├── busan.csv
│   ├── jeju.csv
│   └── seoul.csv
├── docs/
│   └── architecture.md
├── src/
│   └── weather_viz/
│       ├── __init__.py
│       ├── __main__.py
│       ├── fetch.py
│       ├── pipeline.py
│       └── templates/
│           └── report.html
├── tests/
│   ├── test_cli.py
│   ├── test_fetch.py
│   └── test_pipeline.py
├── .gitignore
├── LICENSE
├── README.md
└── pyproject.toml
```

완료된 내부 작업 기록인 `docs/superpowers/`는 제거하고, 외부 독자를 위한 `docs/architecture.md`로 현재 시스템의 수집·누적·렌더링·배포 흐름을 설명한다.

### 4. Python 의존성은 `pyproject.toml`로 통합한다

`requirements.txt`와 `requirements-dev.txt`를 제거한다. 런타임 의존성은 `[project].dependencies`, 테스트 의존성은 `[project.optional-dependencies].dev`에 선언한다.

로컬 개발 설치는 다음 한 줄로 통일한다.

```bash
pip install -e ".[dev]"
```

GitHub Actions는 테스트 도구가 필요하지 않으므로 `pip install -e .`을 사용한다. pip 캐시 키는 `pyproject.toml`을 기준으로 계산한다.

### 5. 파이프라인 경로 계약

파이프라인이 사용하는 경로는 다음과 같이 구분한다.

- 패키지 템플릿: `src/weather_viz/templates/report.html`
- 누적 데이터 입력 및 갱신: 저장소 루트의 `data/`
- 정적 사이트 출력: 저장소 루트의 `site/`

실행 전에 저장소 루트와 템플릿을 검증하는 기존 안전장치를 유지한다. 렌더링 전에 `site/`를 만들고 `.nojekyll`을 생성한다. 기존 `data/`는 이동하거나 초기화하지 않는다.

## GitHub Actions 동작

워크플로는 다음 세 경우에 실행한다.

- 매일 UTC 00:00(KST 09:00) 예약 실행
- `workflow_dispatch` 수동 실행
- `main`의 소스, 템플릿, 패키징 설정 또는 워크플로 변경

작업은 하나의 직렬 흐름으로 실행한다.

1. 저장소 체크아웃
2. Python 설정 및 `pip install -e .`
3. `python -m weather_viz --days 365` 실행
4. 변경된 `data/*.csv`만 조건부 커밋·푸시
5. Pages 설정
6. `site/` 아티팩트 업로드
7. GitHub Pages 배포

권한은 데이터 커밋을 위한 `contents: write`, Pages 배포를 위한 `pages: write`, 배포 인증을 위한 `id-token: write`로 한정한다. 배포 작업은 `github-pages` environment를 사용한다. 기존 `daily-update` 동시성 제어는 유지한다.

## README와 공개 문서

README는 다음 순서로 재구성한다.

1. 프로젝트가 제공하는 결과와 라이브 링크
2. 주요 차트와 데이터 출처
3. 빠른 시작: 환경 생성, 단일 설치 명령, 실행, 테스트
4. 간결한 폴더 구조
5. 데이터 누적 및 자동 배포 방식
6. 상세 구조 문서 링크

`docs/architecture.md`는 Open-Meteo 수집, CSV 증분 누적, Jinja/Plotly 렌더링, Pages 아티팩트 배포를 설명한다. 구현 계획이나 에이전트 작업 절차는 공개 문서에 포함하지 않는다.

## 오류 처리

- 저장소 루트나 템플릿을 찾지 못하면 네트워크 요청과 파일 쓰기 전에 실패한다.
- Open-Meteo 수집 재시도와 `FetchError` 동작은 유지한다.
- 파이프라인 실패 시 셸의 기본 실패 전파로 커밋 및 Pages 배포 단계가 실행되지 않는다.
- CSV에 변경이 없으면 자동 커밋을 생략하지만 HTML 생성 및 Pages 배포는 계속한다.
- Pages 배포가 실패해도 이미 생성된 CSV 이력을 되돌리거나 강제로 재작성하지 않는다.

## 전환 순서

1. 새 `site/` 출력 경로와 Pages 배포 워크플로를 구현하고 로컬에서 검증한다.
2. GitHub Pages 빌드 방식을 `GitHub Actions`로 전환할 준비가 됐는지 확인한다.
3. 루트 HTML 제거를 포함한 구조 변경 PR을 병합한다.
4. 병합된 `main`에서 `workflow_dispatch`를 즉시 실행한다.
5. Pages 배포 성공과 기존 공개 URL을 확인한다.

새 배포가 실패하면 원인을 수정해 같은 Actions 배포를 재실행한다. CSV 이력은 별도 커밋 범위로 유지되므로 HTML 배포 실패를 복구하기 위해 데이터를 되돌리지 않는다.

## 검증

1. 전체 단위 테스트가 통과한다.
2. CLI 실행 후 `site/index.html`, `site/busan.html`, `site/jeju.html`, `site/.nojekyll`이 생성된다.
3. 저장소 루트에는 도시별 HTML이 생성되지 않는다.
4. 기존 `data/*.csv`가 같은 위치에서 증분 갱신된다.
5. 패키지 wheel에 `templates/report.html`이 포함된다.
6. README의 설치 및 실행 명령을 깨끗한 임시 체크아웃에서 재현한다.
7. PR 병합 후 예약 워크플로와 같은 `workflow_dispatch` 실행이 성공한다.
8. Actions 실행 후 데이터 자동 커밋 범위가 `data/*.csv`로 제한됐는지 확인한다.
9. 기존 GitHub Pages URL에서 서울·부산·제주 페이지가 정상적으로 열린다.

## 비범위

- `pipeline.py`를 여러 내부 모듈로 분리하지 않는다.
- CSV 저장 형식이나 데이터 스키마를 바꾸지 않는다.
- 도시 목록, 차트 종류, 페이지 디자인을 바꾸지 않는다.
- 외부 데이터베이스나 별도 스토리지를 도입하지 않는다.
- GitHub Pages의 공개 URL을 바꾸지 않는다.
