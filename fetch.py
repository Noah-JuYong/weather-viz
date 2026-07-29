"""Open-Meteo 일일 날씨 수집 모듈 (과거 관측 + 단기 예보).

전체 파이프라인 중 '수집(fetch)' 구간만 담당한다.
Open-Meteo는 **키/가입 없이 무료**이며 두 엔드포인트를 제공한다:
  - Archive API: 과거~최근 일일 관측치
  - Forecast API: 오늘부터 향후 약 16일 예보

기본 좌표는 서울. 인접 책임(누적 저장/분석/렌더링)은 pipeline.py에서 처리한다.
"""
from __future__ import annotations

from typing import Any

import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

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


def _get(url: str, params: dict[str, Any], session: requests.Session | None) -> dict[str, list[Any]]:
    sess = session or requests
    resp = sess.get(url, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    daily = payload.get("daily") or {}
    if not daily.get("time"):
        raise FetchError(f"날씨 데이터가 비어 있습니다 (url={url}, params={params})")
    return daily


def get_daily_weather(
    start: str,
    end: str,
    *,
    lat: float = SEOUL_LAT,
    lon: float = SEOUL_LON,
    session: requests.Session | None = None,
) -> dict[str, list[Any]]:
    """``start``~``end``(YYYY-MM-DD) 일별 관측치(Archive)를 반환한다."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": DAILY_VARS,
        "start_date": start,
        "end_date": end,
        "timezone": "Asia/Seoul",
    }
    return _get(ARCHIVE_URL, params, session)


def get_forecast(
    *,
    lat: float = SEOUL_LAT,
    lon: float = SEOUL_LON,
    days: int = 8,
    session: requests.Session | None = None,
) -> dict[str, list[Any]]:
    """오늘부터 ``days``일치 일별 예보(Forecast)를 반환한다.

    ``days=8`` 이면 오늘 + 향후 7일. 반환 구조는 Archive와 동일(daily dict).
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": DAILY_VARS,
        "timezone": "Asia/Seoul",
        "forecast_days": days,
    }
    return _get(FORECAST_URL, params, session)
