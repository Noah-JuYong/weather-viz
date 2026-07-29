"""pipeline 분석/저장 로직 검증. 네트워크 없이 동작한다."""
from datetime import date

import pandas as pd

import pipeline
from pipeline import (
    DIM_COLS,
    FACT_COLS,
    append_fact,
    build_charts,
    build_context,
    ensure_movies,
    to_dim_row,
    to_fact_rows,
)


def sample_records():
    return [
        {
            "rank": "1", "movieCd": "20230001", "movieNm": "A",
            "audiCnt": "1000", "audiAcc": "5000", "salesAcc": "50000000",
            "scrnCnt": "100", "showCnt": "300",
        },
        {
            "rank": "2", "movieCd": "20230002", "movieNm": "B",
            "audiCnt": "600", "audiAcc": "2000", "salesAcc": "20000000",
            "scrnCnt": "60", "showCnt": "150",
        },
    ]


def sample_dim():
    return pd.DataFrame(
        [
            {"movieCd": "20230001", "movieNm": "A", "prdtYear": "2023", "openDt": "2023-01-01", "nation": "한국", "genre": "액션"},
            {"movieCd": "20230002", "movieNm": "B", "prdtYear": "2023", "openDt": "2023-02-01", "nation": "미국", "genre": "코미디"},
        ],
        columns=DIM_COLS,
    )


def test_to_fact_rows_columns_and_types(tmp_path):
    df = to_fact_rows("2024-01-01", sample_records())
    assert list(df.columns) == FACT_COLS
    assert len(df) == 2
    assert df.loc[0, "audiCnt"] == 1000
    assert df.loc[1, "movieCd"] == "20230002"


def test_append_fact_is_idempotent(tmp_path):
    path = tmp_path / "boxoffice.csv"
    append_fact(path, "2024-01-01", sample_records())
    # 같은 날을 다시 넣으면 덮어써야 한다(중복 행 없음)
    append_fact(path, "2024-01-01", sample_records())
    df = pipeline.load_fact(path)
    assert len(df) == 2
    # 다른 날은 누적
    append_fact(path, "2024-01-02", sample_records())
    df = pipeline.load_fact(path)
    assert df["date"].nunique() == 2
    assert len(df) == 4


def test_to_dim_row_flattens_nation_genre():
    info = {
        "movieCd": "123", "movieNm": "X", "prdtYear": "2023",
        "openDt": "20240101",
        "nations": [{"nationNm": "한국"}],
        "genres": [{"genreNm": "드라마"}, {"genreNm": "로맨스"}],
    }
    row = to_dim_row(info)
    assert row["nation"] == "한국"
    assert row["genre"] == "드라마"
    assert row["openDt"] == "2024-01-01"


def test_ensure_movies_only_fetches_missing(tmp_path):
    path = tmp_path / "movies.csv"
    pipeline.save_dim(path, sample_dim())
    fetched = []

    def fake_fetcher(cd, session=None):
        fetched.append(cd)
        return {"movieCd": cd, "movieNm": f"movie-{cd}", "nations": [{"nationNm": "한국"}], "genres": [{"genreNm": "액션"}]}

    # 이미 있는 2개 + 새 1개
    result = ensure_movies(path, ["20230001", "20230002", "9999"], fetcher=fake_fetcher)
    assert fetched == ["9999"]  # 이미 있는 건 호출 안 함
    assert len(result) == 3
    assert "9999" in set(result["movieCd"])


def test_build_charts_and_context_on_synthetic(tmp_path):
    fact = pd.concat(
        [
            to_fact_rows("2024-01-01", sample_records()),
            to_fact_rows("2024-01-02", sample_records()),
        ],
        ignore_index=True,
    )
    dim = sample_dim()
    charts = build_charts(fact, dim)
    assert len(charts) == 3
    assert all("plotly-graph-div" in c["html"] for c in charts)

    ctx = build_context(fact, dim)
    assert ctx["empty"] is False
    labels = [k["label"] for k in ctx["kpis"]]
    assert "집계 일수" in labels
    assert ctx["kpis"][0]["value"] == "2024-01-02"  # 최근 일자


def test_build_context_empty():
    ctx = build_context(pd.DataFrame(columns=FACT_COLS), pd.DataFrame(columns=DIM_COLS))
    assert ctx["empty"] is True
    assert ctx["charts"] == []


def test_kst_yesterday_is_recent():
    # 단순 스모크: KST 어제가 오늘-1과 같다.
    assert pipeline.kst_yesterday() == date.fromisoformat(
        (pd.Timestamp.now(tz="Asia/Seoul").date() - pd.Timedelta(days=1)).isoformat()
    )
