"""박스오피스 시각화 파이프라인 본체.

전체 파이프라인에서 수집(fetch.py) 이후 구간을 담당한다:
  1. 누적 저장  — data/boxoffice.csv(팩트), data/movies.csv(영화 차원표)
  2. 분석      — pandas로 일일/누적/장르·국가 비중 집계
  3. 렌더링    — plotly 차드 + Jinja 템플릿으로 index.html 생성

인접 책임: KOBIS API 호출 자체는 fetch.py가 담당. 이 모듈은 네트워크 없이도
분석/렌더링을 검증할 수 있도록 데이터프레임 단위로 동작한다.

실행:
  python pipeline.py                 # KST 어제 일자 1건 갱신
  python pipeline.py --date 20240101 # 특정 일자
  python pipeline.py --backfill 20240101 20240131  # 구간 백필
"""
from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.subplots import make_subplots

import fetch

KST = timezone(timedelta(hours=9))

FACT_COLS = ["date", "rank", "movieCd", "audiCnt", "audiAcc", "salesAcc", "scrnCnt", "showCnt"]
DIM_COLS = ["movieCd", "movieNm", "prdtYear", "openDt", "nation", "genre"]


# --------------------------------------------------------------------------- #
# 날짜 헬퍼
# --------------------------------------------------------------------------- #
def _to_compact(d: date) -> str:
    return d.strftime("%Y%m%d")


def _to_iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_compact(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _compact_to_iso(s: str) -> str:
    """영화정보 openDt(YYYYMMDD) -> YYYY-MM-DD. 빈 값/불량은 그대로."""
    if not s or len(s) != 8 or not s.isdigit():
        return s
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def kst_yesterday() -> date:
    return datetime.now(KST).date() - timedelta(days=1)


# --------------------------------------------------------------------------- #
# 팩트(일일 박스오피스) 저장
# --------------------------------------------------------------------------- #
def load_fact(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=FACT_COLS)
    return pd.read_csv(path, dtype={"movieCd": str})


def save_fact(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df[FACT_COLS].to_csv(path, index=False)


def to_fact_rows(day_iso: str, records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for r in records:
        rows.append(
            {
                "date": day_iso,
                "rank": int(r["rank"]),
                "movieCd": str(r["movieCd"]),
                "audiCnt": int(r["audiCnt"]),
                "audiAcc": int(r["audiAcc"]),
                "salesAcc": int(r.get("salesAcc") or 0),
                "scrnCnt": int(r.get("scrnCnt") or 0),
                "showCnt": int(r.get("showCnt") or 0),
            }
        )
    return pd.DataFrame(rows, columns=FACT_COLS)


def append_fact(path: Path, day_iso: str, records: list[dict[str, Any]]) -> pd.DataFrame:
    """``day_iso`` 하루치를 upsert. 같은 날 다시 돌리면 덮어쓴다(멱등)."""
    df = load_fact(path)
    new = to_fact_rows(day_iso, records)
    if not df.empty:
        df = df[df["date"] != day_iso]
    df = pd.concat([df, new], ignore_index=True)
    df = df.sort_values(["date", "rank"]).reset_index(drop=True)
    save_fact(path, df)
    return df


# --------------------------------------------------------------------------- #
# 차원표(영화 마스터) 저장
# --------------------------------------------------------------------------- #
def load_dim(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=DIM_COLS)
    return pd.read_csv(path, dtype={"movieCd": str})


def save_dim(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df[DIM_COLS].to_csv(path, index=False)


def to_dim_row(info: dict[str, Any]) -> dict[str, Any]:
    nations = info.get("nations") or []
    genres = info.get("genres") or []
    return {
        "movieCd": str(info.get("movieCd", "")),
        "movieNm": info.get("movieNm", ""),
        "prdtYear": info.get("prdtYear", ""),
        "openDt": _compact_to_iso(info.get("openDt", "")),
        "nation": nations[0].get("nationNm", "") if nations else "",
        "genre": genres[0].get("genreNm", "") if genres else "",
    }


def ensure_movies(
    path: Path,
    movie_cds: list[str],
    *,
    fetcher: Callable[..., dict[str, Any] | None] = fetch.get_movie_info,
    session: Any = None,
    sleep: float = 0.15,
) -> pd.DataFrame:
    """차원표에 없는 movieCd만 상세정보를 채워 넣는다(중복 호출 방지)."""
    dim = load_dim(path)
    have = set(dim["movieCd"]) if not dim.empty else set()
    rows = []
    for cd in dict.fromkeys(movie_cds):  # 순서 유지 중복 제거
        if cd in have:
            continue
        try:
            info = fetcher(cd, session=session) if session is not None else fetcher(cd)
        except Exception as exc:  # 개별 영화 실패가 전체를 막지 않도록
            print(f"  movieCd {cd} 상세정보 조회 실패: {exc}")
            continue
        if info:
            rows.append(to_dim_row(info))
            have.add(cd)
            time.sleep(sleep)
    if rows:
        dim = pd.concat([dim, pd.DataFrame(rows, columns=DIM_COLS)], ignore_index=True)
        save_dim(path, dim)
    return dim


# --------------------------------------------------------------------------- #
# 분석 & 차트
# --------------------------------------------------------------------------- #
def _short(name: str, n: int = 14) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def _collapse(series: pd.Series, top_n: int = 6) -> pd.Series:
    """작은 슬라이스를 '기타'로 합친다."""
    if len(series) <= top_n:
        return series
    top = series.nlargest(top_n - 1)
    etc = series.drop(top.index).sum()
    top["기타"] = etc
    return top.sort_values(ascending=False)


def _lookup_name(dim: pd.DataFrame, movie_cd: str) -> str:
    if dim.empty:
        return movie_cd
    hit = dim[dim["movieCd"] == movie_cd]
    return hit.iloc[0]["movieNm"] if not hit.empty else movie_cd


def build_charts(fact: pd.DataFrame, dim: pd.DataFrame) -> list[dict[str, str]]:
    """plotly 차드를 HTML div로 반환. 한 차트 실패해도 나머지는 살린다."""
    charts: list[dict[str, str]] = []
    if fact.empty:
        return charts

    def add(title: str, fig: go.Figure) -> None:
        charts.append({"title": title, "html": fig.to_html(full_html=False, include_plotlyjs=False)})

    latest = fact["date"].max()
    names = dim.set_index("movieCd")["movieNm"].to_dict() if not dim.empty else {}

    # 1) 최근 일자 TOP10 일일 관객수 (가로 바)
    try:
        snap = fact[fact["date"] == latest].sort_values("rank").copy()
        snap["label"] = snap["movieCd"].map(names).fillna(snap["movieCd"]).map(_short)
        fig = go.Figure(
            go.Bar(
                x=snap["audiCnt"].tolist(),
                y=snap["label"].tolist()[::-1],
                orientation="h",
                text=[f"{v:,}명" for v in snap["audiCnt"]],
                textposition="outside",
                marker_color="#4f46e5",
            )
        )
        fig.update_layout(
            title=f"{latest} 일일 관객수 TOP{len(snap)}",
            xaxis_title="관객수(명)",
            margin=dict(l=10, r=30, t=50, b=20),
            height=420,
        )
        add("일일 박스오피스 TOP10", fig)
    except Exception as exc:  # pragma: no cover - 방어 로직
        print(f"TOP10 차트 생성 실패: {exc}")

    # 2) TOP 영화 누적 관객수 추이 (라인)
    try:
        top_cds = fact.groupby("movieCd")["audiAcc"].max().nlargest(5).index.tolist()
        sub = fact[fact["movieCd"].isin(top_cds)].copy()
        sub["name"] = sub["movieCd"].map(names).fillna(sub["movieCd"]).map(_short)
        pivot = sub.pivot_table(index="date", columns="name", values="audiAcc").sort_index()
        fig = go.Figure()
        for col in pivot.columns:
            fig.add_trace(
                go.Scatter(
                    x=pivot.index, y=pivot[col], mode="lines+markers", name=col, connectgaps=True
                )
            )
        fig.update_layout(
            title="누적 관객수 추이 (상위 5편)",
            yaxis_title="누적 관객수(명)",
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.2),
            margin=dict(l=10, r=20, t=50, b=60),
            height=420,
        )
        add("누적 관객수 추이", fig)
    except Exception as exc:  # pragma: no cover
        print(f"추이 차트 생성 실패: {exc}")

    # 3) 장르·국가 비중 (파이 2종)
    try:
        joined = fact.merge(
            dim[["movieCd", "genre", "nation"]], on="movieCd", how="left"
        )
        joined["genre"] = joined["genre"].fillna("기타")
        joined["nation"] = joined["nation"].fillna("기타")
        g = _collapse(joined.groupby("genre")["audiCnt"].sum())
        n = _collapse(joined.groupby("nation")["audiCnt"].sum())
        fig = make_subplots(
            rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]], subplot_titles=["장르", "국가"]
        )
        fig.add_trace(go.Pie(labels=g.index.tolist(), values=g.values.tolist(), hole=0.4), 1, 1)
        fig.add_trace(go.Pie(labels=n.index.tolist(), values=n.values.tolist(), hole=0.4), 1, 2)
        fig.update_layout(title="누적 관객수 비중", margin=dict(l=10, r=10, t=50, b=20), height=420)
        add("장르·국가 비중", fig)
    except Exception as exc:  # pragma: no cover
        print(f"비중 차트 생성 실패: {exc}")

    return charts


def build_context(fact: pd.DataFrame, dim: pd.DataFrame) -> dict[str, Any]:
    generated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    if fact.empty:
        return {
            "updated_at": "—",
            "generated_at": generated_at,
            "kpis": [],
            "charts": [],
            "empty": True,
        }
    latest = fact["date"].max()
    snap = fact[fact["date"] == latest]
    top1 = snap.sort_values("rank").iloc[0]
    kpis = [
        {"label": "최근 일자", "value": latest},
        {"label": "최근 일자 총 관객수", "value": f"{int(snap['audiCnt'].sum()):,}명"},
        {"label": "최근 일자 1위 영화", "value": _lookup_name(dim, top1["movieCd"])},
        {"label": "집계 일수", "value": f"{fact['date'].nunique()}일"},
    ]
    return {
        "updated_at": latest,
        "generated_at": generated_at,
        "kpis": kpis,
        "charts": build_charts(fact, dim),
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
# 실행 단위
# --------------------------------------------------------------------------- #
def run_one(target: date, fact_path: Path, dim_path: Path) -> None:
    records = fetch.get_daily_box_office(_to_compact(target))
    append_fact(fact_path, _to_iso(target), records)
    ensure_movies(dim_path, [str(r["movieCd"]) for r in records])
    print(f"{target}: 일일 {len(records)}건 저장 + 차원표 동기화 완료")


def run_backfill(start: str, end: str, fact_path: Path, dim_path: Path) -> None:
    d = _parse_compact(start)
    end_d = _parse_compact(end)
    if d > end_d:
        raise SystemExit(f"START({start})가 END({end})보다 늦습니다.")
    while d <= end_d:
        try:
            records = fetch.get_daily_box_office(_to_compact(d))
            if records:
                append_fact(fact_path, _to_iso(d), records)
                ensure_movies(dim_path, [str(r["movieCd"]) for r in records])
            print(f"{d}: {len(records)}건")
        except Exception as exc:
            print(f"{d} 실패: {exc}")
        d += timedelta(days=1)
        time.sleep(0.2)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="KOBIS 일일 박스오피스 시각화 파이프라인")
    parser.add_argument("--date", help="특정 일자(YYYYMMDD). 생략 시 KST 어제")
    parser.add_argument(
        "--backfill",
        nargs=2,
        metavar=("START", "END"),
        help="START~END(YYYYMMDD, 포함) 구간 백필",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    fact_path = root / "data" / "boxoffice.csv"
    dim_path = root / "data" / "movies.csv"
    template_path = root / "template.html"
    out_path = root / "index.html"

    if args.backfill:
        run_backfill(args.backfill[0], args.backfill[1], fact_path, dim_path)
    else:
        target = _parse_compact(args.date) if args.date else kst_yesterday()
        run_one(target, fact_path, dim_path)

    fact = load_fact(fact_path)
    dim = load_dim(dim_path)
    context = build_context(fact, dim)
    render(context, template_path, out_path)
    days = fact["date"].nunique() if not fact.empty else 0
    print(f"완료: {out_path.name} 생성 (집계 일수 {days}일)")


if __name__ == "__main__":
    main()
