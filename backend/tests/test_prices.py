"""Tests for the prices service and router.

Network is mocked with `respx` so the suite never touches hvakosterstrommen.no.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from app.schemas import HourPrice
from app.services.prices import (
    NoValidWindowError,
    PricesNotPublishedError,
    UnknownAreaError,
    blocked_hours_from_range,
    cheapest_window,
    fetch_prices,
)


def _hour(h: int, price: float) -> HourPrice:
    return HourPrice(
        NOK_per_kWh=price,
        EUR_per_kWh=price / 11.0,
        EXR=11.0,
        time_start=f"2026-05-21T{h:02d}:00:00+02:00",
        time_end=f"2026-05-21T{(h + 1) % 24:02d}:00:00+02:00",
    )


def _fake_api_payload(prices: list[float]) -> list[dict]:
    return [
        {
            "NOK_per_kWh": p,
            "EUR_per_kWh": p / 11.0,
            "EXR": 11.0,
            "time_start": f"2026-05-21T{i:02d}:00:00+02:00",
            "time_end": f"2026-05-21T{(i + 1) % 24:02d}:00:00+02:00",
        }
        for i, p in enumerate(prices)
    ]


# ---- cheapest_window ---------------------------------------------------------


def test_cheapest_window_picks_lowest_contiguous_block():
    prices = [_hour(i, p) for i, p in enumerate([3, 2, 1, 1, 1, 2, 5, 4])]
    window = cheapest_window(prices, hours=3, area="NO1")
    assert window.start.hour == 2
    assert window.hours == 3
    assert window.total_NOK_per_kWh == pytest.approx(3.0)
    assert window.avg_NOK_per_kWh == pytest.approx(1.0)


def test_cheapest_window_picks_first_when_tied():
    prices = [_hour(i, p) for i, p in enumerate([1, 1, 1, 1])]
    window = cheapest_window(prices, hours=2, area="NO2")
    assert window.start.hour == 0


def test_cheapest_window_handles_hours_larger_than_data():
    prices = [_hour(i, p) for i, p in enumerate([2.0, 1.0, 3.0])]
    window = cheapest_window(prices, hours=99, area="NO1")
    assert window.hours == 3
    assert window.total_NOK_per_kWh == pytest.approx(6.0)


def test_cheapest_window_with_single_hour_window():
    prices = [_hour(i, p) for i, p in enumerate([5, 4, 1, 6])]
    window = cheapest_window(prices, hours=1, area="NO1")
    assert window.start.hour == 2
    assert window.avg_NOK_per_kWh == pytest.approx(1.0)


def test_cheapest_window_normalizes_area_to_uppercase():
    prices = [_hour(0, 1.0)]
    assert cheapest_window(prices, hours=1, area="no3").area == "NO3"


@pytest.mark.parametrize("bad_hours", [0, -1])
def test_cheapest_window_rejects_non_positive_hours(bad_hours):
    with pytest.raises(ValueError, match="hours must be >= 1"):
        cheapest_window([_hour(0, 1.0)], hours=bad_hours, area="NO1")


def test_cheapest_window_rejects_empty_prices():
    with pytest.raises(ValueError, match="prices must not be empty"):
        cheapest_window([], hours=4, area="NO1")


# ---- blocked hours -----------------------------------------------------------


def test_cheapest_window_skips_blocked_hours():
    # Hour 2 is cheapest but blocked; should fall back to next-cheapest contiguous run.
    prices = [_hour(i, p) for i, p in enumerate([5, 4, 1, 1, 1, 3, 2, 2])]
    window = cheapest_window(prices, hours=2, area="NO1", blocked_hours=frozenset({2, 3, 4}))
    assert window.start.hour == 6
    assert window.total_NOK_per_kWh == pytest.approx(4.0)


def test_cheapest_window_raises_when_all_blocked():
    prices = [_hour(i, 1.0) for i in range(4)]
    with pytest.raises(NoValidWindowError):
        cheapest_window(prices, hours=2, area="NO1", blocked_hours=frozenset({0, 1, 2, 3}))


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("08:00", "16:00", set(range(8, 16))),
        ("08:30", "16:45", set(range(8, 16))),  # minutes floored
        ("22:00", "06:00", set(range(22, 24)) | set(range(0, 6))),  # wrap
        ("12:00", "12:00", set()),
        (None, "16:00", set()),
        ("08:00", None, set()),
        ("", "", set()),
    ],
)
def test_blocked_hours_from_range(start, end, expected):
    assert blocked_hours_from_range(start, end) == expected


def test_blocked_hours_from_range_rejects_garbage():
    with pytest.raises(ValueError):
        blocked_hours_from_range("99:00", "16:00")


# ---- fetch_prices ------------------------------------------------------------


@respx.mock
def test_fetch_prices_returns_parsed_rows():
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(return_value=httpx.Response(200, json=_fake_api_payload([1.0, 2.0])))

    rows = fetch_prices(date(2026, 5, 21), "NO1")
    assert len(rows) == 2
    assert rows[0].NOK_per_kWh == 1.0


@respx.mock
def test_fetch_prices_404_raises_not_published():
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(return_value=httpx.Response(404))
    with pytest.raises(PricesNotPublishedError):
        fetch_prices(date(2026, 5, 21), "NO1")


def test_fetch_prices_rejects_unknown_area():
    with pytest.raises(UnknownAreaError):
        fetch_prices(date(2026, 5, 21), "NO9")


@respx.mock
def test_fetch_prices_uppercases_area_in_url():
    route = respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO2.json"
    ).mock(return_value=httpx.Response(200, json=_fake_api_payload([1.0])))
    fetch_prices(date(2026, 5, 21), "no2")
    assert route.called


# ---- router ------------------------------------------------------------------


@respx.mock
def test_get_prices_returns_published_payload(client):
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(return_value=httpx.Response(200, json=_fake_api_payload([1.0, 2.0, 3.0])))

    r = client.get("/api/prices?area=NO1&day=2026-05-21")
    assert r.status_code == 200
    body = r.json()
    assert body["area"] == "NO1"
    assert body["date"] == "2026-05-21"
    assert body["published"] is True
    assert len(body["prices"]) == 3


@respx.mock
def test_get_prices_returns_unpublished_flag_on_404(client):
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(return_value=httpx.Response(404))

    r = client.get("/api/prices?area=NO1&day=2026-05-21")
    assert r.status_code == 200
    body = r.json()
    assert body["published"] is False
    assert body["prices"] == []


def test_get_prices_rejects_bad_area(client):
    r = client.get("/api/prices?area=XX1&day=2026-05-21")
    assert r.status_code == 400


@respx.mock
def test_get_cheapest_returns_window(client):
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(
        return_value=httpx.Response(
            200, json=_fake_api_payload([5, 5, 1, 1, 1, 5, 5, 5])
        )
    )

    r = client.get("/api/prices/cheapest?area=NO1&hours=3&day=2026-05-21")
    assert r.status_code == 200
    body = r.json()
    assert body["hours"] == 3
    assert body["total_NOK_per_kWh"] == pytest.approx(3.0)
    assert body["start"].endswith("02:00:00+02:00")


@respx.mock
def test_get_cheapest_returns_404_when_unpublished(client):
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(return_value=httpx.Response(404))

    r = client.get("/api/prices/cheapest?area=NO1&hours=3&day=2026-05-21")
    assert r.status_code == 404


def test_get_cheapest_validates_hours(client):
    r = client.get("/api/prices/cheapest?area=NO1&hours=99&day=2026-05-21")
    assert r.status_code == 422


def test_get_cheapest_rejects_bad_area(client):
    r = client.get("/api/prices/cheapest?area=XX1&hours=3&day=2026-05-21")
    assert r.status_code == 400


@respx.mock
def test_get_cheapest_honors_away_range(client):
    # Cheapest run is at hours 2-4 but the user is away 02:00-05:00 (blocks 2,3,4).
    # Next-cheapest 2h contiguous run is hours 6-7 (2+2=4).
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(
        return_value=httpx.Response(
            200, json=_fake_api_payload([5, 4, 1, 1, 1, 3, 2, 2])
        )
    )
    r = client.get(
        "/api/prices/cheapest?area=NO1&hours=2&day=2026-05-21"
        "&away_start=02:00&away_end=05:00"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start"].endswith("06:00:00+02:00")
    assert body["total_NOK_per_kWh"] == pytest.approx(4.0)


@respx.mock
def test_get_cheapest_returns_404_when_blocked_eliminates_everything(client):
    respx.get(
        "https://www.hvakosterstrommen.no/api/v1/prices/2026/05-21_NO1.json"
    ).mock(return_value=httpx.Response(200, json=_fake_api_payload([1.0] * 4)))
    r = client.get(
        "/api/prices/cheapest?area=NO1&hours=2&day=2026-05-21"
        "&away_start=00:00&away_end=04:00"
    )
    assert r.status_code == 404
