"""pipeline 분석/저장 로직 검증. 네트워크 없이 동작한다."""
import pandas as pd

import pandas as pd

import pipeline
from pipeline import (
    WEATHER_COLS,
    CITIES,
    build_charts,
    build_context,
    to_weather_rows,
    upsert_weather,
)

SEOUL = next(c for c in CITIES if c["slug"] == "seoul")


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


def test_build_charts_count_with_and_without_forecast():
    h = hist_df()
    # 예보 있으면 5개(기온/강수/월별/극값/예보)
    charts = build_charts(h, forecast_df())
    titles = [c["title"] for c in charts]
    assert "향후 7일 예보" in titles
    assert all("plotly-graph-div" in c["html"] for c in charts)
    # 예보 없으면 4개(예보 차트 제외)
    empty_fc = pd.DataFrame(columns=WEATHER_COLS)
    charts2 = build_charts(h, empty_fc)
    assert len(charts2) == 4
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
