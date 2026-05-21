from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class HourPrice(BaseModel):
    """One hour of spot prices from hvakosterstrommen.no."""

    NOK_per_kWh: float
    EUR_per_kWh: float
    EXR: float
    time_start: datetime
    time_end: datetime


class PricesOut(BaseModel):
    area: str
    date: str
    published: bool
    prices: list[HourPrice]


class ChargeWindow(BaseModel):
    area: str
    hours: int
    start: datetime
    end: datetime
    avg_NOK_per_kWh: float
    total_NOK_per_kWh: float


class HourBucket(BaseModel):
    hour: int
    avg_NOK_per_kWh: float
    count: int


class PriceHistoryOut(BaseModel):
    weekday: list[HourBucket]
    weekend: list[HourBucket]
    missing_days: list[str]
