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
