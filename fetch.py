"""Open-Meteo Archive API 일일 날씨 수집 모듈.

전체 파이프라인 중 '수집(fetch)' 구간만 담당한다.
Open-Meteo Archive API는 **키/가입 없이 무료**로 과거~최근 일일 날씨를 제공한다.
기본 좌표는 서울(37.5665, 126.9780).

인접 책임(누적 저장/분석/렌더링)은 pipeline.py에서 처리한다.
"""
from __future__ import annotations

from typing import Any

import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# 일간 변수: 최고/최저/평균 기온, 강수합, 최대 풍속
DAILY_VARS = (
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
    "precipitation_sum,wind_speed_10m_max"
)

# 기본 좌표: 서울
SEOUL_LAT = 37.5665
SEOUL_LON = 126.9780


class FetchError(RuntimeError):
    """Open-Meteo API 호출/응답 실패."""


def get_daily_weather(
    start: str,
    end: str,
    *,
    lat: float = SEOUL_LAT,
    lon: float = SEOUL_LON,
    session: requests.Session | None = None,
) -> dict[str, list[Any]]:
    """``start``~``end``(YYYY-MM-DD) 일별 날씨를 반환한다.

    반환 dict의 키는 원본 변수명(temperature_2m_max 등) 그대로이며,
    각 값은 일자별 리스트. ``time`` 키에 날짜(YYYY-MM-DD) 리스트가 들어간다.
    정제는 pipeline 쪽에서 수행한다.
    """
    sess = session or requests
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": DAILY_VARS,
        "start_date": start,
        "end_date": end,
        "timezone": "Asia/Seoul",
    }
    resp = sess.get(ARCHIVE_URL, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    daily = payload.get("daily") or {}
    if not daily.get("time"):
        raise FetchError(f"날씨 데이터가 비어 있습니다: {start}~{end} (응답={payload})")
    return daily
