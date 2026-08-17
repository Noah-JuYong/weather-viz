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
