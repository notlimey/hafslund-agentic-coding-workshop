from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from ..schemas import ChargeWindow, PricesOut
from ..services.prices import (
    NoValidWindowError,
    PricesNotPublishedError,
    UnknownAreaError,
    blocked_hours_from_range,
    cheapest_window,
    fetch_prices,
)

OSLO = ZoneInfo("Europe/Oslo")

router = APIRouter()


def _today_oslo() -> date:
    # Prices are indexed by local calendar day in Norway; using UTC would
    # roll over an hour early relative to what users see.
    return datetime.now(OSLO).date()


@router.get("/prices", response_model=PricesOut)
def get_prices(area: str = Query("NO1"), day: date | None = Query(None)):
    target = day or _today_oslo()
    try:
        prices = fetch_prices(target, area)
    except UnknownAreaError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PricesNotPublishedError:
        return PricesOut(
            area=area.upper(), date=target.isoformat(), published=False, prices=[]
        )
    return PricesOut(
        area=area.upper(), date=target.isoformat(), published=True, prices=prices
    )


@router.get("/prices/cheapest", response_model=ChargeWindow)
def get_cheapest_window(
    area: str = Query("NO1"),
    hours: int = Query(4, ge=1, le=24),
    day: date | None = Query(None),
    away_start: str | None = Query(None, description="HH:MM, inclusive"),
    away_end: str | None = Query(None, description="HH:MM, exclusive"),
):
    target = day or _today_oslo()
    try:
        blocked = blocked_hours_from_range(away_start, away_end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        prices = fetch_prices(target, area)
    except UnknownAreaError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PricesNotPublishedError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        return cheapest_window(prices, hours, area, blocked)
    except NoValidWindowError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
