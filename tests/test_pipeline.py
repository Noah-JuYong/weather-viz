"""pipeline 분석/저장 로직 검증. 네트워크 없이 동작한다."""
import pandas as pd

import pipeline
from pipeline import WEATHER_COLS, build_charts, build_context, to_weather_rows, upsert_weather


def sample_daily():
    return {
        "time": ["2024-07-01", "2024-07-02", "2024-07-03"],
        "temperature_2m_max": [33.5, 30.0, 28.1],
        "temperature_2m_min": [25.0, 22.0, 19.0],
        "temperature_2m_mean": [29.0, 26.0, 23.5],
        "precipitation_sum": [0.0, 12.3, 3.4],
        "wind_speed_10m_max": [4.0, 8.0, 6.0],
    }


def test_to_weather_rows_columns_and_values():
    rows = to_weather_rows(sample_daily())
    assert len(rows) == 3
    assert rows[0] == {
        "date": "2024-07-01", "t_max": 33.5, "t_min": 25.0,
        "t_mean": 29.0, "precip": 0.0, "wind_max": 4.0,
    }


def test_upsert_is_idempotent_and_accumulates(tmp_path):
    path = tmp_path / "weather.csv"
    upsert_weather(path, to_weather_rows(sample_daily()))
    # 같은 데이터 다시 넣으면 덮어쓰기(중복 행 없음)
    upsert_weather(path, to_weather_rows(sample_daily()))
    df = pipeline.load_weather(path)
    assert len(df) == 3

    # 다른 날 추가 → 누적
    more = {
        "time": ["2024-07-04"], "temperature_2m_max": [27.0],
        "temperature_2m_min": [18.0], "temperature_2m_mean": [22.5],
        "precipitation_sum": [1.0], "wind_speed_10m_max": [5.0],
    }
    upsert_weather(path, to_weather_rows(more))
    df = pipeline.load_weather(path)
    assert len(df) == 4


def test_build_charts_returns_plotly_divs():
    df = pipeline.load_weather(pipeline.Path("/nonexistent"))  # 빈
    df = pd.DataFrame(to_weather_rows(sample_daily()), columns=WEATHER_COLS)
    df["date"] = pd.to_datetime(df["date"])
    charts = build_charts(df)
    assert len(charts) == 4
    assert all("plotly-graph-div" in c["html"] for c in charts)


def test_build_context_kpis_and_heatwave_count():
    df = pd.DataFrame(to_weather_rows(sample_daily()), columns=WEATHER_COLS)
    df["date"] = pd.to_datetime(df["date"])
    ctx = build_context(df)
    assert ctx["empty"] is False
    labels = [k["label"] for k in ctx["kpis"]]
    assert "관측기간 폭염일수" in labels
    # 7/1만 최고기온 33.5 >= 33 → 폭염 1일
    heat = [k for k in ctx["kpis"] if k["label"] == "관측기간 폭염일수"][0]
    assert heat["value"] == "1일"
    assert ctx["kpis"][0]["value"] == "2024-07-03"  # 최근 관측일


def test_build_context_empty():
    ctx = build_context(pd.DataFrame(columns=WEATHER_COLS))
    assert ctx["empty"] is True
    assert ctx["charts"] == []
