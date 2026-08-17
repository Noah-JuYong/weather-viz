"""다도시 일일 날씨 시각화 파이프라인 본체.

전체 파이프라인에서 수집(fetch.py) 이후 구간을 담당한다:
  1. 누적 저장  — data/<slug>.csv (도시별 일별 관측치)
  2. 예보 통합 — 매 실행마다 단기 예보를 실시간 수집해 관측 추이에 이어붙임
  3. 분석      — 기온 밴드(최고/최저) + 7일 이동평균 + 폭염/한파 기준선,
                 강수량, 월별 통계, 극값 일수, 향후 7일 예보 차트
  4. 렌더링    — plotly + Jinja 템플릿으로 도시별 정적 페이지 생성

데이터 소스(Open-Meteo)는 키/가입 불필요. 분석/렌더링은 네트워크 없이
데이터프레임 단위로 검증할 수 있도록 분리했다.

실행:
  python -m weather_viz                  # 모든 도시, 최근 1년(어제 기준) 갱신
  python -m weather_viz --days 90        # 최근 90일
  python -m weather_viz --backfill 2025-01-01 2025-12-31
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

from . import fetch

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
TEMPLATE_PATH = PACKAGE_ROOT / "templates" / "report.html"

KST = timezone(timedelta(hours=9))

# 기상청 기준 임계값
HEATWAVE_C = 33.0  # 폭염: 일 최고기온 >= 33℃
TROPICAL_C = 25.0  # 열대야: 일 최저기온 >= 25℃
COLDWAVE_C = -12.0  # 한파: 일 최저기온 <= -12℃

WEATHER_COLS = ["date", "t_max", "t_min", "t_mean", "precip", "wind_max"]

# 도시 목록. INDEX_SLUG 에 해당하는 도시가 index.html 이 된다.
INDEX_SLUG = "seoul"
CITIES: list[dict[str, Any]] = [
    {"name": "서울", "slug": "seoul", "lat": 37.5665, "lon": 126.9780},
    {"name": "부산", "slug": "busan", "lat": 35.1796, "lon": 129.0756},
    {"name": "제주", "slug": "jeju", "lat": 33.4996, "lon": 126.5312},
]


# --------------------------------------------------------------------------- #
# 날짜 헬퍼
# --------------------------------------------------------------------------- #
def kst_yesterday() -> str:
    return (datetime.now(KST).date() - timedelta(days=1)).strftime("%Y-%m-%d")


def _shift(iso: str, days: int) -> str:
    return (
        datetime.strptime(iso, "%Y-%m-%d").date() + timedelta(days=days)
    ).strftime("%Y-%m-%d")


def _as_dates(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s)


# --------------------------------------------------------------------------- #
# 누적 저장 (관측치)
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


def refresh_history(path: Path, start: str, end: str, lat: float, lon: float) -> None:
    daily = fetch.get_daily_weather(start, end, lat=lat, lon=lon)
    upsert_weather(path, to_weather_rows(daily))
    print(f"  관측: {start}~{end} → {len(daily['time'])}일 upsert")


def refresh_missing_history(path: Path, start: str, end: str, lat: float, lon: float) -> None:
    """기존 CSV의 마지막 관측일 이후 누락 구간만 수집한다."""
    hist = load_weather(path)
    if not hist.empty:
        next_date = _shift(hist["date"].max().strftime("%Y-%m-%d"), 1)
        start = max(start, next_date)
    if start > end:
        print(f"  관측: {end}까지 최신 (수집 생략)")
        return
    refresh_history(path, start, end, lat, lon)


def forecast_df(lat: float, lon: float, *, after: str | None = None) -> pd.DataFrame:
    """단기 예보를 DataFrame으로 반환. ``after``(YYYY-MM-DD) 이후 날짜만 남긴다.

    예보는 실측이 아니므로 누적 파일에 쓰지 않고 매 실행마다 새로 수집한다.
    """
    daily = fetch.get_forecast(lat=lat, lon=lon)
    df = pd.DataFrame(to_weather_rows(daily), columns=WEATHER_COLS)
    df["date"] = pd.to_datetime(df["date"])
    if after is not None:
        after_dt = pd.to_datetime(after)
        df = df[df["date"] > after_dt]
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 분석 & 차트
# --------------------------------------------------------------------------- #
def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _datestr(s: pd.Series) -> list[str]:
    return s.dt.strftime("%Y-%m-%d").tolist()


def build_charts(hist: pd.DataFrame, fc: pd.DataFrame) -> list[dict[str, str]]:
    charts: list[dict[str, str]] = []
    if hist.empty:
        return charts

    h = hist.copy()
    for c in ["t_max", "t_min", "t_mean", "precip"]:
        h[c] = _num(h[c])
    hd = _datestr(h["date"])

    def add(title: str, fig: go.Figure) -> None:
        charts.append({"title": title, "html": fig.to_html(full_html=False, include_plotlyjs=False)})

    # 1) 기온 추이: 관측 밴드 + 7일 이동평균 + 예보(점선) + 기준선
    try:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=hd, y=h["t_min"], name="최저(관측)",
                line=dict(color="rgba(0,0,0,0)"), hovertemplate="최저 %{y}℃<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=hd, y=h["t_max"], name="최고(관측)", fill="tonexty",
                fillcolor="rgba(239,68,68,0.16)", line=dict(color="#ef4444"),
                hovertemplate="최고 %{y}℃<extra></extra>",
            )
        )
        ma = h["t_mean"].rolling(7, min_periods=1).mean()
        fig.add_trace(
            go.Scatter(
                x=hd, y=ma, name="평균 7일 이동평균", line=dict(color="#0ea5e9", width=2),
                hovertemplate="7일평균 %{y:.1f}℃<extra></extra>",
            )
        )
        if not fc.empty:
            f = fc.copy()
            for c in ["t_max", "t_min"]:
                f[c] = _num(f[c])
            fd = _datestr(f["date"])
            fig.add_trace(
                go.Scatter(
                    x=fd, y=f["t_max"], name="최고(예보)", line=dict(color="#7c3aed", dash="dash"),
                    hovertemplate="예보 최고 %{y}℃<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=fd, y=f["t_min"], name="최저(예보)", line=dict(color="#7c3aed", dash="dot"),
                    hovertemplate="예보 최저 %{y}℃<extra></extra>",
                )
            )
        fig.add_hline(y=HEATWAVE_C, line=dict(color="#dc2626", dash="dash", width=1),
                      annotation_text=f"폭염 {HEATWAVE_C:.0f}℃", annotation_position="top left")
        fig.add_hline(y=COLDWAVE_C, line=dict(color="#2563eb", dash="dash", width=1),
                      annotation_text=f"한파 {COLDWAVE_C:.0f}℃", annotation_position="bottom left")
        fig.update_layout(
            title="일일 기온 (관측 + 예보)", yaxis_title="기온(℃)", hovermode="x unified",
            legend=dict(orientation="h", y=-0.18),
            margin=dict(l=10, r=20, t=50, b=60), height=440,
        )
        add("기온 추이", fig)
    except Exception as exc:  # pragma: no cover
        print(f"기온 차트 실패: {exc}")

    # 1.5) 연간 기온 캘린더 히트맵 (일 평균, GitHub 스타일)
    try:
        dts = h["date"].dt.date
        first = dts.min()
        start_monday = first - timedelta(days=first.weekday())
        n_weeks = ((dts.max() - start_monday).days // 7) + 1
        z = [[float("nan")] * n_weeks for _ in range(7)]  # 행 = 월~일 (0..6)
        week_starts = [start_monday + timedelta(days=7 * w) for w in range(n_weeks)]
        for d, t in zip(dts.values, h["t_mean"].values):
            wi = (d - start_monday).days // 7
            z[d.weekday()][wi] = t
        tickvals, ticktext, prev = [], [], None
        for ws in week_starts:
            if ws.month != prev:
                tickvals.append(ws.strftime("%Y-%m-%d"))
                ticktext.append(f"{ws.month}월")
                prev = ws.month
        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=[ws.strftime("%Y-%m-%d") for ws in week_starts],
                y=["월", "화", "수", "목", "금", "토", "일"],
                colorscale="Turbo", zmin=-15, zmax=35,
                colorbar=dict(title="℃"), xgap=2, ygap=2, hoverongaps=False,
                hovertemplate="%{x}<br>%{y}: %{z:.1f}℃<extra></extra>",
            )
        )
        fig.update_layout(
            title="연간 기온 캘린더 (일 평균)",
            xaxis=dict(tickvals=tickvals, ticktext=ticktext),
            margin=dict(l=10, r=20, t=50, b=20), height=280,
        )
        add("기온 캘린더", fig)
    except Exception as exc:  # pragma: no cover
        print(f"캘린더 차트 실패: {exc}")

    # 2) 일일 강수량
    try:
        fig = go.Figure(go.Bar(x=hd, y=h["precip"], name="강수량", marker_color="#2563eb"))
        fig.update_layout(title="일일 강수량", yaxis_title="강수량(mm)", margin=dict(l=10, r=20, t=50, b=20), height=360)
        add("강수량", fig)
    except Exception as exc:  # pragma: no cover
        print(f"강수 차트 실패: {exc}")

    # 3) 월별 통계
    try:
        m = h.copy()
        m["ym"] = m["date"].dt.strftime("%Y-%m")
        monthly = m.groupby("ym").agg(평균최고기온=("t_max", "mean"), 강수합=("precip", "sum"))
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=False,
            subplot_titles=("월별 평균 최고기온(℃)", "월별 강수합(mm)"), vertical_spacing=0.16,
        )
        fig.add_trace(go.Bar(x=monthly.index, y=monthly["평균최고기온"], marker_color="#f97316", name="평균 최고기온"), 1, 1)
        fig.add_trace(go.Bar(x=monthly.index, y=monthly["강수합"], marker_color="#0ea5e9", name="강수합"), 2, 1)
        fig.update_layout(title="월별 통계", showlegend=False, margin=dict(l=10, r=20, t=50, b=30), height=480)
        add("월별 통계", fig)
    except Exception as exc:  # pragma: no cover
        print(f"월별 차트 실패: {exc}")

    # 4) 극값 일수
    try:
        extremes = {
            "폭염일수": int((h["t_max"] >= HEATWAVE_C).sum()),
            "열대야일수": int((h["t_min"] >= TROPICAL_C).sum()),
            "한파일수": int((h["t_min"] <= COLDWAVE_C).sum()),
        }
        fig = go.Figure(
            go.Bar(
                x=list(extremes.keys()), y=list(extremes.values()),
                marker_color=["#ef4444", "#f59e0b", "#3b82f6"],
                text=list(extremes.values()), textposition="outside",
            )
        )
        fig.update_layout(title="극값 일수 (관측 기간 합계)", yaxis_title="일수", margin=dict(l=10, r=20, t=50, b=30), height=360)
        add("극값 일수", fig)
    except Exception as exc:  # pragma: no cover
        print(f"극값 차트 실패: {exc}")

    # 5) 향후 7일 예보
    if not fc.empty:
        try:
            f = fc.copy()
            for c in ["t_max", "t_min", "precip"]:
                f[c] = _num(f[c])
            fd = _datestr(f["date"])
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=fd, y=f["t_max"], name="최고기온", marker_color="#f97316"), secondary_y=False)
            fig.add_trace(go.Scatter(x=fd, y=f["t_min"], name="최저기온", mode="lines+markers", line=dict(color="#2563eb")), secondary_y=False)
            fig.add_trace(go.Bar(x=fd, y=f["precip"], name="강수량", marker_color="rgba(37,99,235,0.25)"), secondary_y=True)
            fig.update_layout(title="향후 예보 (최고·최저 기온 / 강수량)", barmode="group", margin=dict(l=10, r=20, t=50, b=30), height=380)
            fig.update_yaxes(title_text="기온(℃)", secondary_y=False)
            fig.update_yaxes(title_text="강수량(mm)", secondary_y=True)
            add("향후 7일 예보", fig)
        except Exception as exc:  # pragma: no cover
            print(f"예보 차트 실패: {exc}")

    return charts


def build_context(hist: pd.DataFrame, fc: pd.DataFrame, city: dict[str, Any]) -> dict[str, Any]:
    generated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    nav = [
        {
            "name": c["name"],
            "href": "index.html" if c["slug"] == INDEX_SLUG else f"{c['slug']}.html",
            "active": c["slug"] == city["slug"],
        }
        for c in CITIES
    ]
    base = {
        "city_name": city["name"],
        "generated_at": generated_at,
        "nav": nav,
    }
    if hist.empty:
        return {**base, "updated_at": "—", "kpis": [], "charts": [], "empty": True}
    d = hist.copy()
    for c in ["t_max", "t_min", "t_mean", "precip"]:
        d[c] = _num(d[c])
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
        **base,
        "updated_at": latest.strftime("%Y-%m-%d"),
        "kpis": kpis,
        "charts": build_charts(d, fc),
        "empty": False,
    }


# --------------------------------------------------------------------------- #
# 렌더링
# --------------------------------------------------------------------------- #
def render(context: dict[str, Any], template_path: Path, out_path: Path) -> None:
    env = Environment(loader=FileSystemLoader(template_path.parent), autoescape=select_autoescape(["html"]))
    tmpl = env.get_template(template_path.name)
    out_path.write_text(tmpl.render(**context), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def _page_path(root: Path, slug: str) -> Path:
    name = "index.html" if slug == INDEX_SLUG else f"{slug}.html"
    return root / name


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="다도시 일일 날씨 시각화 파이프라인")
    parser.add_argument("--days", type=int, default=365, help="최근 N일 (기본 365)")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"), help="START~END(YYYY-MM-DD) 구간 백필")
    args = parser.parse_args(argv)

    root = PROJECT_ROOT
    data_dir = root / "data"
    template_path = TEMPLATE_PATH

    end = kst_yesterday()
    if args.backfill:
        start, end = args.backfill
    else:
        start = _shift(end, -(args.days - 1))

    for city in CITIES:
        print(f"[{city['name']}]")
        csv_path = data_dir / f"{city['slug']}.csv"
        if args.backfill:
            refresh_history(csv_path, start, end, city["lat"], city["lon"])
        else:
            refresh_missing_history(csv_path, start, end, city["lat"], city["lon"])
        hist = load_weather(csv_path)
        after = hist["date"].max().strftime("%Y-%m-%d") if not hist.empty else None
        try:
            fc = forecast_df(city["lat"], city["lon"], after=after)
            print(f"  예보: {len(fc)}일")
        except Exception as exc:
            print(f"  예보 수집 실패(건너뜀): {exc}")
            fc = pd.DataFrame(columns=WEATHER_COLS)
        ctx = build_context(hist, fc, city)
        out = _page_path(root, city["slug"])
        render(ctx, template_path, out)
        days = (hist["date"].max() - hist["date"].min()).days + 1 if not hist.empty else 0
        print(f"  → {out.name} (누적 {len(hist)}일 / 기간 {days}일)")


if __name__ == "__main__":
    main()
