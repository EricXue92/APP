import uuid
from datetime import date, time

from pydantic import BaseModel


class WeatherAlert(BaseModel):
    type: str  # "rain", "heat", "uv", "typhoon", "rainstorm"
    severity: str  # "info", "warning", "severe"
    message: str


class WeatherResponse(BaseModel):
    court_id: uuid.UUID
    date: date
    start_time: time | None = None
    temperature: int
    feels_like: int
    humidity: int
    rain_probability: int
    wind_speed_kph: float
    uv_index: int
    condition: str
    condition_icon: str
    alerts: list[WeatherAlert]
    allows_free_cancel: bool
    weather_data_stale: bool = False
