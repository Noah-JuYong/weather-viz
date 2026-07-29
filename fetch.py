"""KOBIS Open API 데이터 수집 모듈.

전체 파이프라인 중 '수집(fetch)' 구간만 담당한다.
  - 일일 박스오피스 목록: searchDailyBoxOfficeList
  - 영화 상세정보(차원표용): searchMovieInfo

인접 책임(누적 저장/분석/렌더링)은 pipeline.py에서 처리한다.
KOBIS 발급 키는 환경변수 ``KOBIS_KEY``로 주입받는다(코드에 평문 금지).
"""
from __future__ import annotations

import os
from typing import Any

import requests

KOBIS_BASE = "http://www.kobis.or.kr/kobisopenapi/webservice/rest"


class FetchError(RuntimeError):
    """KOBIS API 호출 전처리/응답 실패."""


def api_key() -> str:
    """환경변수에서 KOBIS 키를 가져온다. 없으면 FetchError."""
    key = os.environ.get("KOBIS_KEY", "").strip()
    if not key:
        raise FetchError("KOBIS_KEY 환경변수가 설정되지 않았습니다.")
    return key


def get_daily_box_office(
    target_dt: str, *, session: requests.Session | None = None
) -> list[dict[str, Any]]:
    """``target_dt``(YYYYMMDD) 일일 박스오피스 리스트를 반환한다.

    반환 원소는 KOBIS 응답의 ``dailyBoxOfficeList`` 항목 그대로다.
    모든 값은 문자열로 들어오므로 정제는 pipeline 쪽에서 수행한다.
    """
    sess = session or requests
    params = {"key": api_key(), "targetDt": target_dt}
    resp = sess.get(
        f"{KOBIS_BASE}/boxoffice/searchDailyBoxOfficeList.json",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    result = payload.get("boxOfficeResult", {})
    return result.get("dailyBoxOfficeList", [])


def get_movie_info(
    movie_cd: str, *, session: requests.Session | None = None
) -> dict[str, Any] | None:
    """``movieCd`` 영화 상세정보를 반환한다(차원표용). 없으면 None."""
    sess = session or requests
    params = {"key": api_key(), "movieCd": movie_cd}
    resp = sess.get(
        f"{KOBIS_BASE}/movie/searchMovieInfo.json",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("movieInfoResult", {}).get("movieInfo")
