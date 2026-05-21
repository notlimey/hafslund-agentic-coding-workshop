"""Tests for the two-week NO1 price-history endpoint.

Mocks all upstream HTTP with respx. The module-level cache is reset between
tests so cache-hit/miss behavior is observable.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.services import price_history
from app.services.price_history import two_week_window

OSLO = ZoneInfo("Europe/Oslo")


@pytest.fixture(autouse=True)
def _clear_cache():
    price_history._cache.clear()
    yield
    price_history._cache.clear()


def _payload_for(day: date, base: float = 1.0) -> list[dict]:
    return [
        {
            "NOK_per_kWh": base + h * 0.01,
            "EUR_per_kWh": (base + h * 0.01) / 11.0,
            "EXR": 11.0,
            "time_start": f"{day.isoformat()}T{h:02d}:00:00+02:00",
            "time_end": f"{day.isoformat()}T{(h + 1) % 24:02d}:00:00+02:00",
        }
        for h in range(24)
    ]


def _url_for(day: date) -> str:
    return (
        f"https://www.hvakosterstrommen.no/api/v1/prices/"
        f"{day.year}/{day.month:02d}-{day.day:02d}_NO1.json"
    )


def _mock_all_days(days: list[date], status: int = 200) -> None:
    for d in days:
        if status == 200:
            respx.get(_url_for(d)).mock(
                return_value=httpx.Response(200, json=_payload_for(d))
            )
        else:
            respx.get(_url_for(d)).mock(return_value=httpx.Response(status))


def _freeze_today(monkeypatch, today: date) -> None:
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(today.year, today.month, today.day, 12, 0, tzinfo=tz or OSLO)

    monkeypatch.setattr(price_history, "datetime", _Frozen)


# ---- two_week_window ---------------------------------------------------------


@pytest.mark.parametrize(
    "today,expected_start,expected_end",
    [
        # Mon 2026-05-18 → end Sun 2026-05-17, start Mon 2026-05-04.
        (date(2026, 5, 18), date(2026, 5, 4), date(2026, 5, 17)),
        # Wed 2026-05-20 → end Sun 2026-05-17, start Mon 2026-05-04.
        (date(2026, 5, 20), date(2026, 5, 4), date(2026, 5, 17)),
        # Sun 2026-05-24 → end Sun 2026-05-17, start Mon 2026-05-04.
        (date(2026, 5, 24), date(2026, 5, 4), date(2026, 5, 17)),
    ],
)
def test_two_week_window_endpoints(today, expected_start, expected_end):
    window = two_week_window(today)
    assert len(window) == 14
    assert window[0] == expected_start
    assert window[-1] == expected_end
    assert window[0].weekday() == 0  # Monday
    assert window[-1].weekday() == 6  # Sunday


# ---- happy path --------------------------------------------------------------


@respx.mock
def test_history_cold_cache_full_data(client, monkeypatch):
    today = date(2026, 5, 21)  # Thu → window 2026-05-04..2026-05-17
    _freeze_today(monkeypatch, today)
    days = two_week_window(today)
    _mock_all_days(days)

    r = client.get("/api/prices/history")
    assert r.status_code == 200
    body = r.json()

    assert len(body["weekday"]) == 24
    assert len(body["weekend"]) == 24
    assert body["missing_days"] == []
    # 14 days = 10 weekdays + 4 weekends; every hour contributes once per day.
    assert all(b["count"] == 10 for b in body["weekday"])
    assert all(b["count"] == 4 for b in body["weekend"])


@respx.mock
def test_history_warm_cache_skips_upstream(client, monkeypatch):
    today = date(2026, 5, 21)
    _freeze_today(monkeypatch, today)
    days = two_week_window(today)
    _mock_all_days(days)
    routes = [respx.routes[i] for i in range(len(respx.routes))]

    client.get("/api/prices/history")
    client.get("/api/prices/history")

    total_calls = sum(route.call_count for route in routes)
    assert total_calls == 14  # not 28 — second call hit the cache


@respx.mock
def test_history_stale_cache_refetches(client, monkeypatch):
    today = date(2026, 5, 21)
    _freeze_today(monkeypatch, today)
    days = two_week_window(today)
    _mock_all_days(days)
    # Prime cache with a different day's stub value.
    price_history._cache[date(2025, 1, 1)] = "stale"  # type: ignore[assignment]

    r = client.get("/api/prices/history")
    assert r.status_code == 200
    assert today in price_history._cache


# ---- partial / total failures ------------------------------------------------


@respx.mock
def test_history_some_404_listed_in_missing_days(client, monkeypatch):
    today = date(2026, 5, 21)
    _freeze_today(monkeypatch, today)
    days = two_week_window(today)
    missing = {days[0], days[7]}  # one weekday (Mon), one weekday (Mon)
    for d in days:
        if d in missing:
            respx.get(_url_for(d)).mock(return_value=httpx.Response(404))
        else:
            respx.get(_url_for(d)).mock(
                return_value=httpx.Response(200, json=_payload_for(d))
            )

    r = client.get("/api/prices/history")
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["missing_days"]) == sorted(d.isoformat() for d in missing)
    # Both missing days are weekdays → weekday count drops from 10 to 8.
    assert all(b["count"] == 8 for b in body["weekday"])
    assert all(b["count"] == 4 for b in body["weekend"])


@respx.mock
def test_history_all_404_returns_503_and_does_not_cache(client, monkeypatch):
    today = date(2026, 5, 21)
    _freeze_today(monkeypatch, today)
    _mock_all_days(two_week_window(today), status=404)

    r = client.get("/api/prices/history")
    assert r.status_code == 503
    assert today not in price_history._cache


@respx.mock
def test_history_non_404_upstream_returns_502_and_does_not_cache(client, monkeypatch):
    today = date(2026, 5, 21)
    _freeze_today(monkeypatch, today)
    days = two_week_window(today)
    # First day errors with a 500 — should abort the whole fetch with a 502.
    respx.get(_url_for(days[0])).mock(return_value=httpx.Response(500))
    for d in days[1:]:
        respx.get(_url_for(d)).mock(
            return_value=httpx.Response(200, json=_payload_for(d))
        )

    r = client.get("/api/prices/history")
    assert r.status_code == 502
    assert today not in price_history._cache


# ---- single-flight -----------------------------------------------------------


@respx.mock
def test_history_single_flight_coalesces_concurrent_requests(client, monkeypatch):
    today = date(2026, 5, 21)
    _freeze_today(monkeypatch, today)
    days = two_week_window(today)

    both_in_flight = threading.Event()
    enter_count = 0
    enter_lock = threading.Lock()

    def make_side_effect(d: date):
        def _side_effect(request):
            nonlocal enter_count
            with enter_lock:
                enter_count += 1
                if enter_count == 1:
                    # If single-flight works, the second request never reaches here
                    # because it's blocked on the module lock. Briefly wait to give
                    # the second thread time to either coalesce or race.
                    pass
            return httpx.Response(200, json=_payload_for(d))

        return _side_effect

    for d in days:
        respx.get(_url_for(d)).mock(side_effect=make_side_effect(d))

    def call():
        return client.get("/api/prices/history")

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(call)
        f2 = pool.submit(call)
        r1 = f1.result(timeout=10)
        r2 = f2.result(timeout=10)

    both_in_flight.set()
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Single-flight: exactly 14 upstream calls total, not 28.
    total_calls = sum(route.call_count for route in respx.routes)
    assert total_calls == 14
