"""Open-Meteo 수집기의 장애 복원력 검증."""

import pytest
import requests

from weather_viz import fetch


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"daily": {"time": ["2026-08-15"]}}


class TimeoutThenSuccessSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, *, params, timeout):
        self.calls += 1
        if self.calls == 1:
            raise requests.Timeout("temporary timeout")
        return FakeResponse()


class AlwaysTimeoutSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, *, params, timeout):
        self.calls += 1
        raise requests.Timeout("temporary timeout")


def test_get_retries_transient_timeout(monkeypatch):
    session = TimeoutThenSuccessSession()
    monkeypatch.setattr(fetch, "_retry_delay", lambda attempt: None, raising=False)

    daily = fetch._get("https://example.test/weather", {}, session)

    assert daily == {"time": ["2026-08-15"]}
    assert session.calls == 2


def test_get_reports_fetch_error_after_retry_exhaustion(monkeypatch):
    session = AlwaysTimeoutSession()
    monkeypatch.setattr(fetch, "_retry_delay", lambda attempt: None)

    with pytest.raises(fetch.FetchError, match="3회"):
        fetch._get("https://example.test/weather", {}, session)

    assert session.calls == 3
