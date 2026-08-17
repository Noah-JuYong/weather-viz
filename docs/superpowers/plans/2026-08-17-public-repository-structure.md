# Public Repository Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 생성된 HTML을 GitHub Pages 배포 아티팩트로 분리하고, 공개 데이터·소스·테스트·문서만 남는 이해하기 쉬운 저장소 구조를 만든다.

**Architecture:** Python 패키지는 누적 CSV를 저장소 루트의 `data/`에서 읽고 갱신하지만 정적 페이지는 Git에서 제외된 `site/`에 렌더링한다. GitHub Actions의 build 단계는 CSV만 조건부 커밋하고 `site/`를 Pages 아티팩트로 올리며, 별도 deploy 단계가 `github-pages` environment에 게시한다. 의존성과 개발 설치 정보는 `pyproject.toml` 한 곳에 두고 내부 작업 문서는 공개용 아키텍처 문서로 교체한다.

**Tech Stack:** Python 3.11+, pandas, Plotly, Jinja2, requests, pytest, setuptools, GitHub Actions, GitHub Pages

## Global Constraints

- 기존 라이브 URL `https://noah-juyong.github.io/weather-viz/`를 유지한다.
- `data/seoul.csv`, `data/busan.csv`, `data/jeju.csv`의 위치와 CSV 스키마를 바꾸지 않는다.
- 도시 목록, 차트 종류, 페이지 디자인을 바꾸지 않는다.
- `pipeline.py`를 여러 내부 모듈로 분리하지 않는다.
- 생성된 `site/`와 도시별 HTML은 `main`에 커밋하지 않는다.
- 자동 커밋은 `data/*.csv`만 명시적으로 stage한다. `git add -A`를 사용하지 않는다.
- Open-Meteo 재시도, `FetchError`, 저장소·템플릿 사전 검증 동작을 유지한다.
- GitHub 공식 Actions는 2026-08-17 확인 버전인 `checkout@v7`, `setup-python@v7`, `configure-pages@v6`, `upload-pages-artifact@v5`, `deploy-pages@v5`를 사용한다.

---

## File Map

- Modify: `src/weather_viz/pipeline.py` — `data/` 입력과 `site/` 출력을 분리하고 `.nojekyll`을 생성한다.
- Modify: `tests/test_pipeline.py` — 사이트 출력 위치와 렌더링 경로를 회귀 검증한다.
- Create: `tests/test_repository_layout.py` — 공개 파일 구성, 의존성 통합, 워크플로 안전 계약을 검증한다.
- Modify: `pyproject.toml` — 런타임 및 개발 의존성의 단일 진실 공급원이 된다.
- Modify: `.github/workflows/daily.yml` — CSV 커밋과 Pages 아티팩트 배포를 직렬화한다.
- Modify: `.gitignore` — `site/`를 생성물로 제외한다.
- Modify: `README.md` — 방문자가 빠르게 이해할 수 있는 소개·실행·구조 안내를 제공한다.
- Create: `docs/architecture.md` — 수집, 누적, 렌더링, 배포 데이터 흐름을 설명한다.
- Delete: `index.html`, `busan.html`, `jeju.html`, `.nojekyll` — 기존 branch Pages 생성물을 제거한다.
- Delete: `requirements.txt`, `requirements-dev.txt` — `pyproject.toml`로 대체한다.
- Delete: `data/.gitkeep` — 실제 CSV가 있으므로 필요 없는 자리 표시자를 제거한다.
- Delete: `docs/superpowers/` — 완료된 내부 설계·계획을 공개 트리에서 제거한다.

---

### Task 1: 정적 사이트 출력을 `site/`로 격리

**Files:**
- Modify: `src/weather_viz/pipeline.py`
- Modify: `tests/test_pipeline.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `PROJECT_ROOT: Path`, `TEMPLATE_PATH: Path`, `_page_path(root: Path, slug: str) -> Path`
- Produces: `SITE_DIR: Path`, `prepare_site_dir(site_dir: Path) -> None`; `main()`은 모든 HTML을 `SITE_DIR` 아래에 렌더링한다.

- [ ] **Step 1: 사이트 경로 계약의 실패 테스트 작성**

`tests/test_pipeline.py`의 기존 `test_project_paths_keep_generated_outputs_at_repository_root`를 다음 의미로 교체하고, 사이트 준비 테스트를 추가한다.

```python
def test_project_paths_separate_data_and_generated_site():
    assert pipeline.PROJECT_ROOT == Path(__file__).resolve().parents[1]
    assert pipeline.TEMPLATE_PATH == (
        pipeline.PROJECT_ROOT
        / "src"
        / "weather_viz"
        / "templates"
        / "report.html"
    )
    assert pipeline.SITE_DIR == pipeline.PROJECT_ROOT / "site"
    assert pipeline._page_path(pipeline.SITE_DIR, "seoul") == (
        pipeline.SITE_DIR / "index.html"
    )
    assert pipeline._page_path(pipeline.SITE_DIR, "busan") == (
        pipeline.SITE_DIR / "busan.html"
    )


def test_prepare_site_dir_creates_nojekyll(tmp_path):
    site_dir = tmp_path / "site"

    pipeline.prepare_site_dir(site_dir)

    assert site_dir.is_dir()
    assert (site_dir / ".nojekyll").read_text(encoding="utf-8") == ""
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_pipeline.py::test_project_paths_separate_data_and_generated_site \
  tests/test_pipeline.py::test_prepare_site_dir_creates_nojekyll
```

Expected: `SITE_DIR` 또는 `prepare_site_dir` 부재로 FAIL.

- [ ] **Step 3: 사이트 경로와 준비 함수를 최소 구현**

`src/weather_viz/pipeline.py`의 경로 상수와 실행 경로를 다음처럼 변경한다.

```python
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
TEMPLATE_PATH = PACKAGE_ROOT / "templates" / "report.html"
SITE_DIR = PROJECT_ROOT / "site"


def prepare_site_dir(site_dir: Path) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
```

`main()`은 검증 직후 사이트 디렉터리를 준비하고 `_page_path()`에 저장소 루트가 아닌 사이트 경로를 전달한다.

```python
root = PROJECT_ROOT
data_dir = root / "data"
site_dir = SITE_DIR
template_path = TEMPLATE_PATH
validate_project_paths(root, template_path)
prepare_site_dir(site_dir)

# 도시 루프 안
out = _page_path(site_dir, city["slug"])
```

기존 `test_main_backfill_refreshes_exact_requested_range`가 저장소의 실제 `site/`를 만들지 않도록 `tmp_path` 인자를 받고 다음 monkeypatch를 추가한다.

```python
monkeypatch.setattr(pipeline, "SITE_DIR", tmp_path / "site")
```

- [ ] **Step 4: 세 도시가 모두 `site/`로 렌더링되는 통합 단위 테스트 작성**

`tests/test_pipeline.py`에 다음 테스트를 추가한다.

```python
def test_main_renders_all_city_pages_into_site(tmp_path, monkeypatch):
    site_dir = tmp_path / "site"
    rendered = []
    monkeypatch.setattr(pipeline, "SITE_DIR", site_dir)
    monkeypatch.setattr(pipeline, "refresh_missing_history", lambda *args: None)
    monkeypatch.setattr(
        pipeline, "load_weather", lambda path: pd.DataFrame(columns=WEATHER_COLS)
    )
    monkeypatch.setattr(
        pipeline,
        "forecast_df",
        lambda lat, lon, after=None: pd.DataFrame(columns=WEATHER_COLS),
    )
    monkeypatch.setattr(pipeline, "build_context", lambda hist, fc, city: {})
    monkeypatch.setattr(
        pipeline,
        "render",
        lambda context, template_path, out_path: rendered.append(out_path),
    )

    pipeline.main([])

    assert rendered == [
        site_dir / "index.html",
        site_dir / "busan.html",
        site_dir / "jeju.html",
    ]
    assert (site_dir / ".nojekyll").is_file()
```

- [ ] **Step 5: `site/`를 Git에서 제외하고 전체 테스트 실행**

`.gitignore`의 배포 관련 주석을 다음으로 교체한다.

```gitignore
# Generated GitHub Pages artifact
site/

# data/*.csv is public cumulative source data and remains tracked.
```

Run:

```bash
.venv/bin/pytest -q
git check-ignore -v site/index.html
git diff --check
```

Expected: 모든 테스트 PASS, `site/index.html`은 `.gitignore`의 `site/` 규칙에 매칭, whitespace 오류 없음.

- [ ] **Step 6: Task 1 커밋**

```bash
git add .gitignore src/weather_viz/pipeline.py tests/test_pipeline.py
git commit -m "refactor: render generated pages into site directory"
```

---

### Task 2: 의존성을 `pyproject.toml`로 통합

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_repository_layout.py`
- Delete: `requirements.txt`
- Delete: `requirements-dev.txt`

**Interfaces:**
- Consumes: setuptools `src` 패키지 설정과 `weather_viz/templates/report.html` package-data 계약
- Produces: `pip install -e .` 런타임 설치와 `pip install -e ".[dev]"` 개발 설치 계약

- [ ] **Step 1: 단일 의존성 공급원의 실패 테스트 작성**

`tests/test_repository_layout.py`를 생성한다.

```python
"""공개 저장소 구조와 운영 설정의 회귀 테스트."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_dependencies_live_in_pyproject_only():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["project"]["dependencies"] == [
        "requests>=2.31",
        "pandas>=2.0",
        "plotly>=5.18",
        "jinja2>=3.1",
    ]
    assert config["project"]["optional-dependencies"]["dev"] == ["pytest>=7.4"]
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "requirements-dev.txt").exists()
```

- [ ] **Step 2: 테스트가 기존 분산 설정 때문에 실패하는지 확인**

Run:

```bash
.venv/bin/pytest -q tests/test_repository_layout.py::test_dependencies_live_in_pyproject_only
```

Expected: `[project].dependencies` 부재 또는 requirements 파일 존재로 FAIL.

- [ ] **Step 3: `pyproject.toml`에 의존성 선언**

`[project]`에 다음 내용을 추가한다.

```toml
dependencies = [
    "requests>=2.31",
    "pandas>=2.0",
    "plotly>=5.18",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=7.4"]
```

`requirements.txt`와 `requirements-dev.txt`를 삭제한다.

- [ ] **Step 4: 깨끗한 가상환경에서 설치 계약 검증**

저장소 내부에 새 가상환경을 만들지 말고 임시 경로를 사용한다.

```bash
verify_venv=$(mktemp -d /tmp/weather-viz-venv.XXXXXX)
python3 -m venv "$verify_venv"
"$verify_venv/bin/pip" install -e ".[dev]"
"$verify_venv/bin/python" -m pytest -q
```

Expected: 설치 성공, 전체 테스트 PASS. 네트워크 제한으로 실패하면 같은 명령에 승인된 네트워크 권한을 사용해 한 번 재실행한다.

- [ ] **Step 5: Task 2 커밋**

```bash
git add pyproject.toml tests/test_repository_layout.py
git rm requirements.txt requirements-dev.txt
git commit -m "build: consolidate dependencies in pyproject"
```

---

### Task 3: Actions에서 CSV 커밋과 Pages 배포를 분리

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `tests/test_repository_layout.py`

**Interfaces:**
- Consumes: Task 1의 `site/` 출력, Task 2의 `pip install -e .` 계약
- Produces: `update` job이 `github-pages` 아티팩트를 만들고 `deploy` job이 해당 아티팩트를 Pages에 게시하는 워크플로

- [ ] **Step 1: 워크플로 안전 계약의 실패 테스트 작성**

`tests/test_repository_layout.py`에 다음 테스트를 추가한다.

```python
def test_daily_workflow_deploys_site_without_committing_generated_files():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8"
    )

    assert "pip install -e ." in workflow
    assert "git add data/*.csv" in workflow
    assert "git add -A" not in workflow
    assert "actions/configure-pages@v6" in workflow
    assert "actions/upload-pages-artifact@v5" in workflow
    assert "include-hidden-files: true" in workflow
    assert "actions/deploy-pages@v5" in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
```

- [ ] **Step 2: 기존 워크플로에서 테스트가 실패하는지 확인**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_repository_layout.py::test_daily_workflow_deploys_site_without_committing_generated_files
```

Expected: 새 설치 명령, 제한된 git add 또는 Pages Actions 부재로 FAIL.

- [ ] **Step 3: `daily.yml`을 build/update와 deploy 흐름으로 교체**

워크플로를 다음 계약으로 작성한다.

```yaml
name: Daily weather update

on:
  push:
    branches: [main]
    paths:
      - '.github/workflows/daily.yml'
      - 'src/**'
      - 'pyproject.toml'
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: daily-update
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install package
        run: pip install -e .

      - name: Fetch, analyze, and render
        run: python -m weather_viz --days 365

      - name: Commit data changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/*.csv
          if git diff --cached --quiet; then
            echo "no data changes"
          else
            git commit -m "chore: daily weather update ($(date -u +%Y-%m-%d))"
            git push
          fi

      - name: Configure Pages
        uses: actions/configure-pages@v6

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v5
        with:
          path: site
          include-hidden-files: true

  deploy:
    needs: update
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v5
```

`${{ ... }}`는 계획을 구현할 때 위 YAML 그대로 보존한다.

- [ ] **Step 4: 워크플로 정적 검증과 전체 테스트**

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/daily.yml", aliases: true)'
.venv/bin/pytest -q
git diff --check
```

Expected: YAML parse 성공, 전체 테스트 PASS, whitespace 오류 없음.

- [ ] **Step 5: Task 3 커밋**

```bash
git add .github/workflows/daily.yml tests/test_repository_layout.py
git commit -m "ci: deploy generated site with GitHub Pages actions"
```

---

### Task 4: 공개 문서와 최상위 파일 정리

**Files:**
- Modify: `README.md`
- Create: `docs/architecture.md`
- Modify: `tests/test_repository_layout.py`
- Delete: `index.html`
- Delete: `busan.html`
- Delete: `jeju.html`
- Delete: `.nojekyll`
- Delete: `data/.gitkeep`
- Delete: `docs/superpowers/`

**Interfaces:**
- Consumes: Task 1의 `site/` 출력, Task 2의 단일 설치 명령, Task 3의 Pages 배포 흐름
- Produces: 외부 방문자가 README와 `docs/architecture.md`만으로 실행 및 데이터 흐름을 이해할 수 있는 최종 공개 트리

- [ ] **Step 1: 최종 공개 트리의 실패 테스트 작성**

`tests/test_repository_layout.py`에 다음 테스트를 추가한다.

```python
def test_generated_pages_and_internal_plans_are_not_tracked_at_root():
    for name in ["index.html", "busan.html", "jeju.html", ".nojekyll"]:
        assert not (ROOT / name).exists()

    assert not (ROOT / "docs" / "superpowers").exists()
    assert not (ROOT / "data" / ".gitkeep").exists()
    assert (ROOT / "docs" / "architecture.md").is_file()
```

- [ ] **Step 2: 기존 생성물과 내부 문서 때문에 테스트가 실패하는지 확인**

Run:

```bash
.venv/bin/pytest -q \
  tests/test_repository_layout.py::test_generated_pages_and_internal_plans_are_not_tracked_at_root
```

Expected: 루트 HTML, `docs/superpowers`, 또는 누락된 `docs/architecture.md` 때문에 FAIL.

- [ ] **Step 3: `docs/architecture.md` 작성**

문서는 다음 내용을 포함하되 구현 계획이나 에이전트 절차를 포함하지 않는다.

```markdown
# Architecture

## Overview

weather-viz는 Open-Meteo의 관측·예보 데이터를 도시별 CSV에 누적하고,
Plotly와 Jinja로 정적 리포트를 생성해 GitHub Pages에 배포한다.

## Data flow

Open-Meteo → `data/*.csv` → pandas/Plotly → `site/*.html` → GitHub Pages

## Repository boundaries

- `src/weather_viz/`: 수집과 리포트 생성 코드
- `data/`: Git에서 이력을 추적하는 공개 누적 데이터
- `site/`: 실행 때만 생성되는 Pages 아티팩트
- `tests/`: 네트워크 없이 실행되는 회귀 테스트

## Automation

예약 또는 수동 Actions 실행이 데이터를 갱신하고, CSV만 커밋한 뒤
생성된 `site/`를 Pages 아티팩트로 배포한다.
```

실제 문서에서는 각 단계의 실패 방식, 증분 수집 이유, HTML을 추적하지 않는 이유를 한 단락씩 설명한다.

- [ ] **Step 4: README를 외부 방문자 순서로 재작성**

README에는 다음 명령을 정확히 사용한다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m weather_viz
pytest
```

구조도에는 `.github/`, `data/`, `docs/architecture.md`, `src/weather_viz/`, `tests/`, `pyproject.toml`만 표시한다. 생성된 HTML이 Git에 없지만 Actions에서 `site/`로 만들어 Pages에 배포된다는 설명과 `[상세 구조](docs/architecture.md)` 링크를 포함한다.

- [ ] **Step 5: 레거시 생성물과 내부 작업 문서 제거**

정확히 다음 추적 파일을 제거한다.

```bash
git rm index.html busan.html jeju.html .nojekyll data/.gitkeep
git rm -r docs/superpowers
```

다른 데이터 파일이나 문서를 삭제하지 않는다.

- [ ] **Step 6: 공개 트리와 문서 검증**

```bash
.venv/bin/pytest -q
git ls-files | sort
git diff --check
```

Expected:

- 전체 테스트 PASS
- 루트 HTML, `.nojekyll`, requirements 파일, `docs/superpowers`, `data/.gitkeep`이 추적 목록에 없음
- `docs/architecture.md`, `data/*.csv`, `src/weather_viz/**`, `tests/**`가 추적 목록에 있음

- [ ] **Step 7: Task 4 커밋**

```bash
git add README.md docs/architecture.md tests/test_repository_layout.py
git commit -m "docs: simplify public repository layout"
```

`git rm`으로 stage된 삭제도 같은 커밋에 포함한다.

---

### Task 5: 최종 검증, Pages 전환, PR 및 운영 확인

**Files:**
- Verify only: 전체 저장소
- External setting: `Noah-JuYong/weather-viz` GitHub Pages `build_type`

**Interfaces:**
- Consumes: Tasks 1–4의 최종 브랜치
- Produces: Actions 기반 Pages 배포와 기존 URL의 검증된 공개 사이트

- [ ] **Step 1: 최종 로컬 검증**

```bash
.venv/bin/pytest -q
.venv/bin/python -m weather_viz --help
git diff --check origin/main..HEAD
git status --short --branch
```

Expected: 전체 테스트 PASS, CLI help exit 0, diff check clean, 의도하지 않은 변경 없음. 로컬 실행이 만든 `site/`는 ignored 상태여야 한다.

- [ ] **Step 2: 깨끗한 임시 체크아웃에서 실제 파이프라인 실행**

```bash
verify_dir=$(mktemp -d /tmp/weather-viz-public.XXXXXX)
git archive HEAD | tar -x -C "$verify_dir"
project_python="$PWD/.venv/bin/python"
(cd "$verify_dir" && PYTHONPATH="$verify_dir/src" \
  "$project_python" -u -m weather_viz --days 365)
test -f "$verify_dir/site/index.html"
test -f "$verify_dir/site/busan.html"
test -f "$verify_dir/site/jeju.html"
test -f "$verify_dir/site/.nojekyll"
test ! -e "$verify_dir/index.html"
```

Expected: 세 도시 수집·렌더링 성공, 사이트 파일은 `site/`에만 존재.

같은 임시 체크아웃에서 wheel과 package-data를 검증한다.

```bash
wheel_dir=$(mktemp -d /tmp/weather-viz-wheel.XXXXXX)
"$project_python" -m pip wheel --no-deps --wheel-dir "$wheel_dir" "$verify_dir"
unzip -l "$wheel_dir"/weather_viz-0.1.0-py3-none-any.whl \
  | rg 'weather_viz/templates/report.html'
```

Expected: wheel 빌드 성공 및 템플릿 경로 출력. 모든 빌드 부산물은 임시 체크아웃 안에만 생성된다.

- [ ] **Step 3: 독립 코드 리뷰**

`superpowers:requesting-code-review`를 사용해 `origin/main..HEAD` 범위를 리뷰한다. Critical과 Important 이슈를 수정하고 전체 테스트를 다시 실행한다.

- [ ] **Step 4: 브랜치 푸시와 상세 한글 PR 생성**

PR 본문은 다음을 포함한다.

- 왜 루트 HTML이 외부 방문자에게 혼란을 줬는지
- `main`의 최종 폴더 구조
- HTML은 없어지는 것이 아니라 Pages 아티팩트로 이동한다는 설명
- CSV가 계속 `main`에 남는 이유
- 의존성 및 문서 통합
- 로컬·wheel·실제 렌더링 검증 결과
- Pages 설정 전환과 병합 후 확인 절차

- [ ] **Step 5: GitHub Pages 빌드 방식 전환**

병합 직전에 현재 설정을 확인한다.

```bash
gh api repos/Noah-JuYong/weather-viz/pages \
  --jq '{build_type,source,html_url,status}'
```

Expected before change: `build_type`은 `legacy`, source는 `main`의 `/`.

사용자가 승인한 범위에 따라 Pages를 workflow 방식으로 전환한다.

```bash
gh api --method PUT repos/Noah-JuYong/weather-viz/pages \
  -f build_type=workflow
```

다시 조회해 `build_type: workflow`를 확인한다. 토큰 값은 출력하거나 파일에 저장하지 않는다.

- [ ] **Step 6: PR 병합 후 Actions 수동 실행**

저장소에서 허용하는 병합 방식으로 PR을 병합한다. 병합으로 발생한 `push` 실행이 있으면 해당 실행을 감시하고, 없거나 재검증이 필요하면 다음을 실행한다.

```bash
gh workflow run daily.yml --repo Noah-JuYong/weather-viz --ref main
run_id=$(gh run list --repo Noah-JuYong/weather-viz \
  --workflow daily.yml --branch main --event workflow_dispatch --limit 1 \
  --json databaseId --jq '.[0].databaseId')
gh run watch "$run_id" --repo Noah-JuYong/weather-viz --exit-status
```

Expected: `update`와 `deploy` job 모두 SUCCESS. 각 단계에서 새 공식 Actions 버전이 사용되고 Node.js 20 deprecation 경고가 없어야 한다.

- [ ] **Step 7: 최신 `main`과 라이브 사이트 검증**

```bash
git fetch origin main
main_dir=$(mktemp -d /tmp/weather-viz-main.XXXXXX)
git archive origin/main | tar -x -C "$main_dir"
project_pytest="$PWD/.venv/bin/pytest"
(cd "$main_dir" && PYTHONPATH="$main_dir/src" "$project_pytest" -q tests)
```

이어서 라이브 URL의 HTTP 200과 도시 탭을 확인한다.

```bash
curl --fail --silent --show-error \
  https://noah-juyong.github.io/weather-viz/ | rg '서울'
curl --fail --silent --show-error \
  https://noah-juyong.github.io/weather-viz/busan.html | rg '부산'
curl --fail --silent --show-error \
  https://noah-juyong.github.io/weather-viz/jeju.html | rg '제주'
```

Expected: 최신 `main` 테스트 PASS, 세 URL 모두 HTTP 성공 및 해당 도시명 포함.

- [ ] **Step 8: 완료 상태 기록**

PR URL, Actions 실행 URL, 최신 `main` 테스트 수, Pages `build_type: workflow`, 라이브 URL 세 개의 검증 결과를 사용자에게 보고한다. 기능 브랜치는 별도 삭제 요청이 없으면 보존한다.
