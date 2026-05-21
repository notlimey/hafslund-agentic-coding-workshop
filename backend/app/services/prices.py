"""Norwegian spot-price fetch and cheapest-window selection.

Mirrors the URL + area validation in `strompris-mcp/src/strompris_mcp/__init__.py`
intentionally: the MCP server runs in a separate process for the LLM, so we
duplicate ~5 lines rather than import across process boundaries.
"""

from __future__ import annotations

from datetime import date

import httpx

from ..schemas import ChargeWindow, HourPrice

API_URL = (
    "https://www.hvakosterstrommen.no/api/v1/prices/"
    "{year}/{month:02d}-{day:02d}_{area}.json"
)
VALID_AREAS = frozenset({"NO1", "NO2", "NO3", "NO4", "NO5"})


class UnknownAreaError(ValueError):
    """Raised when the price area is not one of NO1..NO5."""


class PricesNotPublishedError(LookupError):
    """Raised when hvakosterstrommen.no has no prices for the given day yet."""


class NoValidWindowError(LookupError):
    """Raised when no contiguous window fits outside the blocked hours."""


def fetch_prices(day: date, area: str) -> list[HourPrice]:
    """Fetch hourly spot prices for one day and price area.

    Raises:
        UnknownAreaError: if `area` is not in VALID_AREAS.
        PricesNotPublishedError: if the upstream returns 404 (prices for the
            next day are typically published around 13:00 CET).
    """
    area = area.upper()
    if area not in VALID_AREAS:
        raise UnknownAreaError(
            f"area must be one of {sorted(VALID_AREAS)}; got {area!r}"
        )

    url = API_URL.format(year=day.year, month=day.month, day=day.day, area=area)
    response = httpx.get(url, timeout=10.0)
    if response.status_code == 404:
        raise PricesNotPublishedError(f"no prices for {day.isoformat()} in {area}")
    response.raise_for_status()
    return [HourPrice.model_validate(row) for row in response.json()]


def cheapest_window(
    prices: list[HourPrice],
    hours: int,
    area: str,
    blocked_hours: frozenset[int] = frozenset(),
) -> ChargeWindow:
    """Find the contiguous `hours`-long window with the lowest total NOK/kWh.

    Assumes `prices` is sorted by `time_start` (the upstream API guarantees this).
    Skips any window that overlaps a local hour-of-day in `blocked_hours`.
    Falls back to the full range when `hours` >= len(prices) so we still return
    something useful on partial days.
    """
    if not prices:
        raise ValueError("prices must not be empty")
    if hours < 1:
        raise ValueError(f"hours must be >= 1; got {hours}")

    window_len = min(hours, len(prices))
    best_start: int | None = None
    best_sum = float("inf")
    for i in range(len(prices) - window_len + 1):
        window = prices[i : i + window_len]
        if any(p.time_start.hour in blocked_hours for p in window):
            continue
        total = sum(p.NOK_per_kWh for p in window)
        if total < best_sum:
            best_sum = total
            best_start = i

    if best_start is None:
        raise NoValidWindowError(
            f"no {window_len}h window fits outside blocked hours {sorted(blocked_hours)}"
        )

    window = prices[best_start : best_start + window_len]
    return ChargeWindow(
        area=area.upper(),
        hours=window_len,
        start=window[0].time_start,
        end=window[-1].time_end,
        avg_NOK_per_kWh=best_sum / window_len,
        total_NOK_per_kWh=best_sum,
    )


def blocked_hours_from_range(away_start: str | None, away_end: str | None) -> frozenset[int]:
    """Parse a HH:MM..HH:MM "away" range into a set of hour-of-day ints.

    Conventions: `away_start` is inclusive, `away_end` is exclusive (so 08:00–16:00
    blocks 8,9,…,15 — eight working hours). Equal or empty inputs mean "no blocking".
    Wraps across midnight when end < start (e.g. 22:00–06:00 blocks 22,23,0,…,5).
    Minutes are floored to the hour — the upstream price granularity is hourly.
    """
    if not away_start or not away_end:
        return frozenset()
    start_h = _parse_hour(away_start)
    end_h = _parse_hour(away_end)
    if start_h == end_h:
        return frozenset()
    if start_h < end_h:
        return frozenset(range(start_h, end_h))
    return frozenset(list(range(start_h, 24)) + list(range(0, end_h)))


def _parse_hour(hhmm: str) -> int:
    h_str, _, _ = hhmm.partition(":")
    h = int(h_str)
    if not 0 <= h <= 23:
        raise ValueError(f"hour must be 0..23; got {hhmm!r}")
    return h
