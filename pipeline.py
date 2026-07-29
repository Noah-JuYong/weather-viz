"""서울 일일 날씨 시각화 파이프라인 본체.

전체 파이프라인에서 수집(fetch.py) 이후 구간을 담당한다:
  1. 누적 저장  — data/weather.csv (일별 기온/강수/풍속)
  2. 분석      — pandas로 추이/월별/극값(폭염·열대야·한파) 집계
  3. 렌더링    — plotly 차트 + Jinja 템플릿으로 index.html 생성

데이터 소스(Open-Meteo)는 키/가입 불필요. fetch 이후 구간은 네트워크 없이도
데이터프레임 단위로 검증할 수 있도록 분리했다.

실행:
  python pipeline.py                  # 최근 1년(어제 기준) 갱신
  python pipeline.py --days 90        # 최근 90일
  python pipeline.py --backfill 2025-01-01 2025-12-31
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.subplots import make_subplots

import fetch

KST = timezone(timedelta(hours=9))

# 기상청 기준 임계값
HEATWAVE_C = 33.0  # 폭염: 일 최고기온 >= 33℃
TROPICAL_C = 25.0  # 열대야: 일 최저기온 >= 25℃
COLDWAVE_C = -12.0  # 한파: 일 최저기온 <= -12℃

WEATHER_COLS = ["date", "t_max", "t_min", "t_mean", "precip", "wind_max"]


# --------------------------------------------------------------------------- #
# 날짜 헬퍼
# --------------------------------------------------------------------------- #
def kst_yesterday() -> str:
    return (datetime.now(KST).date() - timedelta(days=1)).strftime("%Y-%m-%d")


def _shift(iso: str, days: int) -> str:
    return (
        datetime.strptime(iso, "%Y-%m-%d").date() + timedelta(days=days)
    ).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# 누적 저장
# --------------------------------------------------------------------------- #
def load_weather(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=WEATHER_COLS)
    return pd.read_csv(path, parse_dates=["date"])


def save_weather(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df[WEATHER_COLS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)


def to_weather_rows(daily: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Open-Meteo daily 응답 → 행 리스트."""
    rows = []
    for i, d in enumerate(daily["time"]):
        rows.append(
            {
                "date": d,
                "t_max": daily["temperature_2m_max"][i],
                "t_min": daily["temperature_2m_min"][i],
                "t_mean": daily["temperature_2m_mean"][i],
                "precip": daily["precipitation_sum"][i],
                "wind_max": daily["wind_speed_10m_max"][i],
            }
        )
    return rows


def upsert_weather(path: Path, rows: list[dict[str, Any]]) -> pd.DataFrame:
    """행들을 date 키로 upsert(같은 날은 최신값으로 덮어쓰기)."""
    new = pd.DataFrame(rows, columns=WEATHER_COLS)
    new["date"] = pd.to_datetime(new["date"])
    df = load_weather(path)
    if not df.empty:
        keep = set(new["date"].dt.strftime("%Y-%m-%d"))
        df = df[~df["date"].dt.strftime("%Y-%m-%d").isin(keep)]
    df = pd.concat([df, new], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    save_weather(path, df)
    return df


# --------------------------------------------------------------------------- #
# 분석 & 차트
# --------------------------------------------------------------------------- #
def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def build_charts(df: pd.DataFrame) -> list[dict[str, str]]:
    charts: list[dict[str, str]] = []
    if df.empty:
        return charts
    d = df.copy()
    d["t_max"] = _safe_num(d["t_max"])
    d["t_min"] = _safe_num(d["t_min"])
    d["t_mean"] = _safe_num(d["t_mean"])
    d["precip"] = _safe_num(d["precip"])
    dates = d["date"].dt.strftime("%Y-%m-%d")

    def add(title: str, fig: go.Figure) -> None:
        charts.append(
            {"title": title, "html": fig.to_html(full_html=False, include_plotlyjs=False)}
        )

    # 1) 일일 기온 밴드(최고~최저) + 평균 기온선
    try:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates, y=d["t_min"], name="최저기온",
                line=dict(color="rgba(0,0,0,0)"), hovertemplate="최저 %{y}℃<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=d["t_max"], name="최고기온", fill="tonexty",
                fillcolor="rgba(239,68,68,0.18)", line=dict(color="#ef4444"),
                hovertemplate="최고 %{y}℃<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates, y=d["t_mean"], name="평균기온", line=dict(color="#0ea5e9", width=1.5),
                hovertemplate="평균 %{y}℃<extra></extra>",
            )
        )
        fig.update_layout(
            title="일일 기온 (최고·평균·최저)",
            yaxis_title="기온(℃)", hovermode="x unified",
            legend=dict(orientation="h", y=-0.15),
            margin=dict(l=10, r=20, t=50, b=50), height=420,
        )
        add("기온 추이", fig)
    except Exception as exc:  # pragma: no cover
        print(f"기온 차트 실패: {exc}")

    # 2) 일일 강수량
    try:
        fig = go.Figure(
            go.Bar(x=dates, y=d["precip"], name="강수량", marker_color="#2563eb")
        )
        fig.update_layout(
            title="일일 강수량", yaxis_title="강수량(mm)",
            margin=dict(l=10, r=20, t=50, b=20), height=360,
        )
        add("강수량", fig)
    except Exception as exc:  # pragma: no cover
        print(f"강수 차트 실패: {exc}")

    # 3) 월별 통계 (평균 최고기온 / 강수합)
    try:
        d["ym"] = d["date"].dt.strftime("%Y-%m")
        monthly = d.groupby("ym").agg(평균최고기온=("t_max", "mean"), 강수합=("precip", "sum"))
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=False,
            subplot_titles=("월별 평균 최고기온(℃)", "월별 강수합(mm)"),
            vertical_spacing=0.16,
        )
        fig.add_trace(
            go.Bar(x=monthly.index, y=monthly["평균최고기온"], marker_color="#f97316", name="평균 최고기온"),
            1, 1,
        )
        fig.add_trace(
            go.Bar(x=monthly.index, y=monthly["강수합"], marker_color="#0ea5e9", name="강수합"),
            2, 1,
        )
        fig.update_layout(
            title="월별 통계", showlegend=False,
            margin=dict(l=10, r=20, t=50, b=30), height=480,
        )
        add("월별 통계", fig)
    except Exception as exc:  # pragma: no cover
        print(f"월별 차트 실패: {exc}")

    # 4) 극값 일수 (폭염/열대야/한파)
    try:
        extremes = {
            "폭염일수": int((d["t_max"] >= HEATWAVE_C).sum()),
            "열대야일수": int((d["t_min"] >= TROPICAL_C).sum()),
            "한파일수": int((d["t_min"] <= COLDWAVE_C).sum()),
        }
        fig = go.Figure(
            go.Bar(
                x=list(extremes.keys()), y=list(extremes.values()),
                marker_color=["#ef4444", "#f59e0b", "#3b82f6"],
                text=list(extremes.values()), textposition="outside",
            )
        )
        fig.update_layout(
            title="극값 일수 (관측 기간 합계)",
            yaxis_title="일수", margin=dict(l=10, r=20, t=50, b=30), height=360,
        )
        add("극값 일수", fig)
    except Exception as exc:  # pragma: no cover
        print(f"극값 차트 실패: {exc}")

    return charts


def build_context(df: pd.DataFrame) -> dict[str, Any]:
    generated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    if df.empty:
        return {
            "updated_at": "—", "generated_at": generated_at,
            "kpis": [], "charts": [], "empty": True,
        }
    d = df.copy()
    for c in ["t_max", "t_min", "t_mean", "precip"]:
        d[c] = _safe_num(d[c])
    latest = d["date"].max()
    latest_row = d[d["date"] == latest].iloc[0]
    days = (d["date"].max() - d["date"].min()).days + 1
    kpis = [
        {"label": "최근 관측일", "value": latest.strftime("%Y-%m-%d")},
        {"label": "최근 기온(최고/최저)", "value": f"{latest_row['t_max']:.1f} / {latest_row['t_min']:.1f}℃"},
        {"label": "관측 기간", "value": f"{days}일"},
        {"label": "관측기간 폭염일수", "value": f"{int((d['t_max'] >= HEATWAVE_C).sum())}일"},
    ]
    return {
        "updated_at": latest.strftime("%Y-%m-%d"),
        "generated_at": generated_at,
        "kpis": kpis,
        "charts": build_charts(d),
        "empty": False,
    }


# --------------------------------------------------------------------------- #
# 렌더링
# --------------------------------------------------------------------------- #
def render(context: dict[str, Any], template_path: Path, out_path: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(["html"]),
    )
    tmpl = env.get_template(template_path.name)
    out_path.write_text(tmpl.render(**context), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def refresh(path: Path, start: str, end: str) -> None:
    daily = fetch.get_daily_weather(start, end)
    rows = to_weather_rows(daily)
    upsert_weather(path, rows)
    print(f"수집: {start}~{end} → {len(rows)}일 upsert 완료")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="서울 일일 날씨 시각화 파이프라인")
    parser.add_argument("--days", type=int, default=365, help="최근 N일 (기본 365)")
    parser.add_argument(
        "--backfill", nargs=2, metavar=("START", "END"),
        help="START~END(YYYY-MM-DD, 포함) 구간 백필",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    data_path = root / "data" / "weather.csv"
    template_path = root / "template.html"
    out_path = root / "index.html"

    end = kst_yesterday()
    if args.backfill:
        start, end = args.backfill
    else:
        start = _shift(end, -(args.days - 1))

    refresh(data_path, start, end)

    df = load_weather(data_path)
    context = build_context(df)
    render(context, template_path, out_path)
    days = (df["date"].max() - df["date"].min()).days + 1 if not df.empty else 0
    print(f"완료: {out_path.name} 생성 (누적 {len(df)}일 / 기간 {days}일)")


if __name__ == "__main__":
    main()
