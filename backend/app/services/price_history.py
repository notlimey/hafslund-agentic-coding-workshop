"""Two-week weekday-vs-weekend NO1 price profile with a daily in-memory cache.

The cache holds one entry keyed by today's Europe/Oslo calendar date. Concurrent
cache-miss callers serialize on a single `threading.Lock` — FastAPI runs sync
endpoints on a threadpool, so the lock both protects the dict and acts as the
single-flight gate (REQ-006). The 14 sequential upstream fetches take a few
seconds at most, so serializing the cold-cache path is acceptable.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from ..schemas import HourBucket, HourPrice, PriceHistoryOut
from .prices import PricesNotPublishedError, fetch_prices

OSLO = ZoneInfo("Europe/Oslo")
AREA = "NO1"

_cache: dict[date, PriceHistoryOut] = {}
_lock = threading.Lock()


class HistoryUpstreamError(RuntimeError):
    """Non-404 upstream failure during the 14-day fetch."""


class HistoryAllMissingError(LookupError):
    """All 14 target days returned 404 — no historical data available."""


def two_week_window(today: date) -> list[date]:
    # End on the Sunday of the most-recent fully-completed ISO week.
    # weekday(): Mon=0..Sun=6 → days back to that Sunday is weekday()+1
    # (Mon→1 day back, Sun→7 days back — the week that ended *today* is not
    # yet complete until the day rolls over).
    end_sunday = today - timedelta(days=today.weekday() + 1)
    start_monday = end_sunday - timedelta(days=13)
    return [start_monday + timedelta(days=i) for i in range(14)]


def get_history() -> PriceHistoryOut:
    today = datetime.now(OSLO).date()
    with _lock:
        cached = _cache.get(today)
        if cached is not None:
            return cached
        profile = _compute_profile(two_week_window(today))
        _cache[today] = profile
        return profile


def _compute_profile(days: list[date]) -> PriceHistoryOut:
    per_day: dict[date, list[HourPrice]] = {}
    missing: list[date] = []
    for d in days:
        try:
            per_day[d] = fetch_prices(d, AREA)
        except PricesNotPublishedError:
            missing.append(d)
        except httpx.HTTPError as e:
            raise HistoryUpstreamError(
                f"upstream failure fetching {d.isoformat()}: {e}"
            ) from e
    if not per_day:
        raise HistoryAllMissingError(
            f"no historical NO1 prices available for {days[0].isoformat()}..{days[-1].isoformat()}"
        )
    return _aggregate(per_day, missing)


def _aggregate(
    per_day: dict[date, list[HourPrice]], missing: list[date]
) -> PriceHistoryOut:
    weekday_sums = [0.0] * 24
    weekday_counts = [0] * 24
    weekend_sums = [0.0] * 24
    weekend_counts = [0] * 24

    for d, prices in per_day.items():
        is_weekend = d.weekday() >= 5
        sums = weekend_sums if is_weekend else weekday_sums
        counts = weekend_counts if is_weekend else weekday_counts
        for p in prices:
            # Index by the hour-of-day in Oslo local time; upstream payload is
            # tz-aware (CET/CEST), so .hour after astimezone(OSLO) is correct.
            h = p.time_start.astimezone(OSLO).hour
            sums[h] += p.NOK_per_kWh
            counts[h] += 1

    return PriceHistoryOut(
        weekday=[_bucket(h, weekday_sums[h], weekday_counts[h]) for h in range(24)],
        weekend=[_bucket(h, weekend_sums[h], weekend_counts[h]) for h in range(24)],
        missing_days=[d.isoformat() for d in missing],
    )


def _bucket(hour: int, total: float, count: int) -> HourBucket:
    avg = total / count if count else 0.0
    return HourBucket(hour=hour, avg_NOK_per_kWh=avg, count=count)
