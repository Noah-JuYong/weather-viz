# Project Structure Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python 소스와 템플릿을 `src/weather_viz/` 패키지로 옮기면서 GitHub Pages 결과물과 데이터는 저장소 루트에 그대로 유지한다.

**Architecture:** `weather_viz` 패키지가 수집과 파이프라인 구현을 소유하고 `__main__.py`가 CLI 진입점을 제공한다. 파이프라인은 패키지 위치에서 저장소 루트를 계산해 기존 `data/*.csv`와 도시별 HTML을 같은 위치에 생성하며, Jinja 템플릿만 패키지 내부에서 읽는다.

**Tech Stack:** Python 3.11+, setuptools src layout, pytest, pandas, Plotly, Jinja2, GitHub Actions

## Global Constraints

- GitHub Pages는 `main` 브랜치의 `/root`에서 계속 배포한다.
- `index.html`, `busan.html`, `jeju.html`, `data/*.csv`의 경로와 형식을 바꾸지 않는다.
- 일반 실행의 증분 수집과 `--backfill START END` 전체 구간 수집 동작을 유지한다.
- Open-Meteo 재시도 정책과 데이터 스키마를 변경하지 않는다.
- 이번 작업에서는 `pipeline.py` 내부 책임을 별도 모듈로 분리하지 않는다.
- 의존성 목록은 `requirements.txt`와 `requirements-dev.txt`에 계속 둔다.

---

### Task 1: Python 소스와 템플릿을 `src/weather_viz`로 이동

**Files:**
- Create: `src/weather_viz/__init__.py`
- Move: `fetch.py` → `src/weather_viz/fetch.py`
- Move: `pipeline.py` → `src/weather_viz/pipeline.py`
- Move: `template.html` → `src/weather_viz/templates/report.html`
- Modify: `tests/test_fetch.py`
- Modify: `tests/test_pipeline.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: 기존 `fetch.get_daily_weather`, `fetch.get_forecast`, `pipeline.main` 및 분석·저장 함수
- Produces: `weather_viz.fetch`, `weather_viz.pipeline`, `pipeline.PROJECT_ROOT: Path`, `pipeline.TEMPLATE_PATH: Path`

- [ ] **Step 1: 테스트 import를 새 패키지 경로로 변경**

`tests/test_fetch.py`:

```python
from weather_viz import fetch
```

`tests/test_pipeline.py`:

```python
from weather_viz import pipeline
from weather_viz.pipeline import (
    WEATHER_COLS,
    CITIES,
    build_charts,
    build_context,
    refresh_missing_history,
    to_weather_rows,
    upsert_weather,
)
```

- [ ] **Step 2: 테스트가 패키지 부재로 실패하는지 확인**

Run: `.venv/bin/pytest -q`

Expected: collection 단계에서 `ModuleNotFoundError: No module named 'weather_viz'`

- [ ] **Step 3: src layout을 pytest 경로로 설정**

`pyproject.toml`의 pytest 설정을 다음처럼 변경한다.

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: 기존 파일을 패키지 위치로 이동**

```bash
mkdir -p src/weather_viz/templates
git mv fetch.py src/weather_viz/fetch.py
git mv pipeline.py src/weather_viz/pipeline.py
git mv template.html src/weather_viz/templates/report.html
```

`src/weather_viz/__init__.py`:

```python
"""Open-Meteo 기반 다도시 날씨 수집·시각화 패키지."""
```

- [ ] **Step 5: 패키지 상대 import와 경로 상수를 적용**

`src/weather_viz/pipeline.py`에서:

```python
from . import fetch

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
TEMPLATE_PATH = PACKAGE_ROOT / "templates" / "report.html"
```

`main()`의 경로 계산은 다음으로 교체한다.

```python
root = PROJECT_ROOT
data_dir = root / "data"
template_path = TEMPLATE_PATH
```

모듈 docstring의 실행 예시는 `python -m weather_viz` 형식으로 갱신한다.

- [ ] **Step 6: 기존 동작 테스트를 실행**

Run: `.venv/bin/pytest -q`

Expected: 기존 9개 테스트 PASS

- [ ] **Step 7: 변경을 커밋**

```bash
git add pyproject.toml src/weather_viz tests/test_fetch.py tests/test_pipeline.py
git commit -m "refactor: move weather code into src package"
```

---

### Task 2: 모듈 CLI와 패키지 설치 설정 추가

**Files:**
- Create: `src/weather_viz/__main__.py`
- Create: `tests/test_cli.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/daily.yml`

**Interfaces:**
- Consumes: `weather_viz.pipeline.main(argv: list[str] | None = None) -> None`
- Produces: `python -m weather_viz [--days N | --backfill START END]`

- [ ] **Step 1: 모듈 CLI 도움말 회귀 테스트 작성**

`tests/test_cli.py`:

```python
import subprocess
import sys


def test_module_cli_exposes_help():
    result = subprocess.run(
        [sys.executable, "-m", "weather_viz", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "다도시 일일 날씨 시각화 파이프라인" in result.stdout
    assert "--backfill" in result.stdout
```

- [ ] **Step 2: 진입점 부재로 테스트가 실패하는지 확인**

Run: `.venv/bin/pytest -q tests/test_cli.py`

Expected: FAIL, stderr에 `No module named weather_viz.__main__`

- [ ] **Step 3: `__main__.py` 구현**

`src/weather_viz/__main__.py`:

```python
from .pipeline import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: setuptools src layout 설정 추가**

`pyproject.toml`에 다음 설정을 추가한다.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "weather-viz"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
weather_viz = ["templates/*.html"]
```

- [ ] **Step 5: CLI 테스트가 통과하는지 확인**

Run: `.venv/bin/pytest -q tests/test_cli.py`

Expected: 1 PASS

- [ ] **Step 6: Actions 설치와 실행 명령 변경**

`.github/workflows/daily.yml`:

```yaml
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install --no-deps -e .

      - name: Fetch + analyze + render
        run: python -m weather_viz --days 365
```

- [ ] **Step 7: editable 설치와 전체 테스트 실행**

Run: `.venv/bin/pip install --no-deps -e .`

Expected: `weather-viz-0.1.0` editable 설치 성공

Run: `.venv/bin/pytest -q`

Expected: 10개 테스트 PASS

- [ ] **Step 8: 변경을 커밋**

```bash
git add pyproject.toml src/weather_viz/__main__.py tests/test_cli.py .github/workflows/daily.yml
git commit -m "refactor: run pipeline as weather_viz module"
```

---

### Task 3: 저장소 안내와 통합 경로 검증

**Files:**
- Modify: `README.md`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `pipeline.PROJECT_ROOT`, `pipeline.TEMPLATE_PATH`, `pipeline.main`
- Produces: 저장소 루트의 기존 HTML·CSV 출력 계약과 새 사용자 실행 안내

- [ ] **Step 1: 출력 경로 계약 테스트 작성**

`tests/test_pipeline.py`에 다음 테스트를 추가한다.

```python
def test_project_paths_keep_generated_outputs_at_repository_root():
    assert pipeline.PROJECT_ROOT == Path(__file__).resolve().parents[1]
    assert pipeline.TEMPLATE_PATH == (
        pipeline.PROJECT_ROOT / "src" / "weather_viz" / "templates" / "report.html"
    )
    assert pipeline._page_path(pipeline.PROJECT_ROOT, "seoul") == (
        pipeline.PROJECT_ROOT / "index.html"
    )
    assert pipeline._page_path(pipeline.PROJECT_ROOT, "busan") == (
        pipeline.PROJECT_ROOT / "busan.html"
    )
```

`from pathlib import Path`도 추가한다.

- [ ] **Step 2: 출력 경로 계약 테스트 실행**

Run: `.venv/bin/pytest -q tests/test_pipeline.py::test_project_paths_keep_generated_outputs_at_repository_root`

Expected: PASS. Task 1의 경로 계산이 틀렸다면 FAIL해야 한다.

- [ ] **Step 3: README 구조와 명령 갱신**

README의 구조 트리를 선택한 `src/weather_viz/` 구조로 바꾸고 다음 명령을 안내한다.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install --no-deps -e .

python -m weather_viz
python -m weather_viz --days 90
python -m weather_viz --backfill 2025-01-01 2025-12-31
pytest
```

도시 설정 위치 안내를 `src/weather_viz/pipeline.py`로 변경한다.

- [ ] **Step 4: 네트워크 없는 전체 검증**

Run: `.venv/bin/pytest -q`

Expected: 11개 테스트 PASS

Run: `git diff --check`

Expected: 출력 없음, exit 0

- [ ] **Step 5: 임시 복사본에서 실제 파이프라인 검증**

현재 브랜치를 `/tmp` 아래 임시 디렉터리로 내보낸 뒤 editable 설치하고 실행한다.

```bash
verify_dir=$(mktemp -d /tmp/weather-viz-structure.XXXXXX)
git archive HEAD | tar -x -C "$verify_dir"
python -m pip install --no-deps -e "$verify_dir"
cd "$verify_dir"
python -m weather_viz --days 365
```

Expected:

- 서울·부산·제주 관측 및 예보 수집 성공
- `$verify_dir/index.html`, `$verify_dir/busan.html`, `$verify_dir/jeju.html` 존재
- `$verify_dir/data/seoul.csv`, `$verify_dir/data/busan.csv`, `$verify_dir/data/jeju.csv` 존재
- `src/weather_viz/` 아래에는 생성 HTML이나 CSV가 생기지 않음

- [ ] **Step 6: 문서와 검증 테스트 커밋**

```bash
git add README.md tests/test_pipeline.py
git commit -m "docs: update project layout and commands"
```

- [ ] **Step 7: 게시 전 최종 검증**

Run: `.venv/bin/pytest -q && git diff --check && git status -sb`

Expected: 11개 테스트 PASS, diff 오류 없음, 작업 트리 깨끗함
