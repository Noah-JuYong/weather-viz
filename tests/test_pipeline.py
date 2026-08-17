"""pipeline 분석/저장 로직 검증. 네트워크 없이 동작한다."""
from pathlib import Path

import pandas as pd
import pytest

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

SEOUL = next(c for c in CITIES if c["slug"] == "seoul")


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


def test_main_fails_before_io_when_project_root_is_invalid(tmp_path, monkeypatch):
    invalid_root = tmp_path / "not-a-checkout"
    invalid_root.mkdir()
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", invalid_root)
    monkeypatch.setattr(
        pipeline, "TEMPLATE_PATH", invalid_root / "templates" / "report.html"
    )
    monkeypatch.setattr(
        pipeline,
        "refresh_missing_history",
        lambda *args, **kwargs: pytest.fail("경로 검증 전에 수집하면 안 됩니다"),
    )

    with pytest.raises(RuntimeError, match="저장소 루트"):
        pipeline.main([])


def test_main_fails_before_io_when_template_is_missing(tmp_path, monkeypatch):
    package_dir = tmp_path / "src" / "weather_viz"
    package_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").touch()
    missing_template = package_dir / "templates" / "report.html"
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "TEMPLATE_PATH", missing_template)
    monkeypatch.setattr(
        pipeline,
        "refresh_missing_history",
        lambda *args, **kwargs: pytest.fail("경로 검증 전에 수집하면 안 됩니다"),
    )

    with pytest.raises(RuntimeError, match="템플릿"):
        pipeline.main([])


def sample_daily():
    return {
        "time": ["2024-07-01", "2024-07-02", "2024-07-03"],
        "temperature_2m_max": [33.5, 30.0, 28.1],
        "temperature_2m_min": [25.0, 22.0, 19.0],
        "temperature_2m_mean": [29.0, 26.0, 23.5],
        "precipitation_sum": [0.0, 12.3, 3.4],
        "wind_speed_10m_max": [4.0, 8.0, 6.0],
    }


def hist_df():
    df = pd.DataFrame(to_weather_rows(sample_daily()), columns=WEATHER_COLS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def forecast_df():
    rows = [
        {"date": "2024-07-04", "t_max": 30.0, "t_min": 23.0, "t_mean": 26.5, "precip": 1.0, "wind_max": 5.0},
        {"date": "2024-07-05", "t_max": 31.0, "t_min": 24.0, "t_mean": 27.5, "precip": 0.0, "wind_max": 4.5},
    ]
    df = pd.DataFrame(rows, columns=WEATHER_COLS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_to_weather_rows():
    rows = to_weather_rows(sample_daily())
    assert len(rows) == 3
    assert rows[0]["t_max"] == 33.5 and rows[0]["date"] == "2024-07-01"


def test_upsert_idempotent_and_accumulates(tmp_path):
    path = tmp_path / "seoul.csv"
    upsert_weather(path, to_weather_rows(sample_daily()))
    upsert_weather(path, to_weather_rows(sample_daily()))  # 덮어쓰기
    assert len(pipeline.load_weather(path)) == 3
    upsert_weather(path, to_weather_rows({
        "time": ["2024-07-04"], "temperature_2m_max": [27.0], "temperature_2m_min": [18.0],
        "temperature_2m_mean": [22.5], "precipitation_sum": [1.0], "wind_speed_10m_max": [5.0],
    }))
    assert len(pipeline.load_weather(path)) == 4


def test_refresh_missing_history_fetches_only_after_latest_date(tmp_path, monkeypatch):
    path = tmp_path / "seoul.csv"
    upsert_weather(path, to_weather_rows(sample_daily()))
    calls = []

    def fake_get_daily_weather(start, end, *, lat, lon):
        calls.append((start, end, lat, lon))
        return {
            "time": ["2024-07-04"],
            "temperature_2m_max": [27.0],
            "temperature_2m_min": [18.0],
            "temperature_2m_mean": [22.5],
            "precipitation_sum": [1.0],
            "wind_speed_10m_max": [5.0],
        }

    monkeypatch.setattr(pipeline.fetch, "get_daily_weather", fake_get_daily_weather)

    refresh_missing_history(path, "2023-07-06", "2024-07-04", 37.5, 127.0)

    assert calls == [("2024-07-04", "2024-07-04", 37.5, 127.0)]
    assert pipeline.load_weather(path)["date"].max() == pd.Timestamp("2024-07-04")


def test_main_backfill_refreshes_exact_requested_range(tmp_path, monkeypatch):
    calls = []

    def fake_refresh(path, start, end, lat, lon):
        calls.append((path.name, start, end, lat, lon))

    def fail_incremental(*args, **kwargs):
        raise AssertionError("--backfill must not use incremental refresh")

    monkeypatch.setattr(pipeline, "refresh_history", fake_refresh)
    monkeypatch.setattr(pipeline, "SITE_DIR", tmp_path / "site")
    monkeypatch.setattr(pipeline, "refresh_missing_history", fail_incremental)
    monkeypatch.setattr(
        pipeline, "load_weather", lambda path: pd.DataFrame(columns=WEATHER_COLS)
    )
    monkeypatch.setattr(
        pipeline, "forecast_df", lambda lat, lon, after=None: pd.DataFrame(columns=WEATHER_COLS)
    )
    monkeypatch.setattr(pipeline, "build_context", lambda hist, fc, city: {})
    monkeypatch.setattr(pipeline, "render", lambda context, template_path, out_path: None)

    pipeline.main(["--backfill", "2024-01-01", "2024-01-31"])

    assert [(name, start, end) for name, start, end, _, _ in calls] == [
        ("seoul.csv", "2024-01-01", "2024-01-31"),
        ("busan.csv", "2024-01-01", "2024-01-31"),
        ("jeju.csv", "2024-01-01", "2024-01-31"),
    ]


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


def test_build_charts_count_with_and_without_forecast():
    h = hist_df()
    # 예보 있으면 6개(기온/캘린더/강수/월별/극값/예보)
    charts = build_charts(h, forecast_df())
    titles = [c["title"] for c in charts]
    assert "기온 캘린더" in titles
    assert "향후 7일 예보" in titles
    assert all("plotly-graph-div" in c["html"] for c in charts)
    # 예보 없으면 5개(예보 차트 제외, 캘린더 포함)
    empty_fc = pd.DataFrame(columns=WEATHER_COLS)
    charts2 = build_charts(h, empty_fc)
    assert len(charts2) == 5
    assert "향후 7일 예보" not in [c["title"] for c in charts2]


def test_build_context_nav_and_kpis():
    ctx = build_context(hist_df(), forecast_df(), SEOUL)
    assert ctx["empty"] is False
    assert ctx["city_name"] == "서울"
    slugs = [(t["name"], t["href"], t["active"]) for t in ctx["nav"]]
    assert ("서울", "index.html", True) in slugs
    assert any(name == "부산" and href == "busan.html" for name, href, _ in slugs)
    heat = [k for k in ctx["kpis"] if k["label"] == "관측기간 폭염일수"][0]
    assert heat["value"] == "1일"  # 7/1만 33.5>=33


def test_build_context_empty():
    empty = pd.DataFrame(columns=WEATHER_COLS)
    ctx = build_context(empty, empty, SEOUL)
    assert ctx["empty"] is True
    assert ctx["charts"] == []
    assert ctx["city_name"] == "서울"
