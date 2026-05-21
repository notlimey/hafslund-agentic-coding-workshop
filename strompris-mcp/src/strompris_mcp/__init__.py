from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP

API_URL = "https://www.hvakosterstrommen.no/api/v1/prices/{year}/{month:02d}-{day:02d}_{area}.json"
VALID_AREAS = {"NO1", "NO2", "NO3", "NO4", "NO5"}

mcp = FastMCP("strompris")


@mcp.tool()
def get_electricity_price(date: str, area: str) -> list[dict]:
    """Fetch Norwegian spot electricity prices for one day and price area.

    Args:
        date: ISO date in YYYY-MM-DD format (e.g. "2026-05-17").
        area: Price area, one of NO1, NO2, NO3, NO4, NO5.

    Returns:
        List of hourly price entries from hvakosterstrommen.no. Each entry
        includes NOK_per_kWh, EUR_per_kWh, EXR, time_start, time_end.
    """
    area = area.upper()
    if area not in VALID_AREAS:
        raise ValueError(f"area must be one of {sorted(VALID_AREAS)}; got {area!r}")

    try:
        year_s, month_s, day_s = date.split("-")
        year, month, day = int(year_s), int(month_s), int(day_s)
    except ValueError as e:
        raise ValueError(f"date must be YYYY-MM-DD; got {date!r}") from e

    url = API_URL.format(year=year, month=month, day=day, area=area)
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    return response.json()


def main() -> None:
    mcp.run()
