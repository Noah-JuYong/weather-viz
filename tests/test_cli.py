"""weather_viz 모듈 실행 진입점 검증."""

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
