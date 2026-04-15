import json
import logging
from datetime import date, datetime, time, timedelta, timezone

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import t
from app.redis import redis_client
from app.schemas.weather import WeatherAlert, WeatherResponse

logger = logging.getLogger(__name__)


def _round_coord(val: float) -> str:
    """Round coordinate to 2 decimal places for cache key (~1.1km grid)."""
    return f"{val:.2f}"


def _cache_key(lat: float, lon: float, query_date: date, query_time: time | None) -> str:
    """Build Redis cache key. Coordinates are pre-rounded floats or raw."""
    lat_s = _round_coord(lat)
    lon_s = _round_coord(lon)
    date_s = query_date.isoformat()
    if query_time is None:
        return f"weather:{lat_s}:{lon_s}:{date_s}:day"
    block = (query_time.hour // 3) * 3
    return f"weather:{lat_s}:{lon_s}:{date_s}:{block}"


def _cache_ttl(query_date: date) -> int:
    """Return TTL in seconds based on how far out the date is."""
    days_out = (query_date - date.today()).days
    if days_out <= 1:
        return 1800  # 30 minutes
    elif days_out <= 3:
        return 3600  # 1 hour
    else:
        return 10800  # 3 hours


def _compute_alerts(
    temperature: int,
    rain_probability: int,
    uv_index: int,
    warnings: list[dict],
    lang: str,
) -> tuple[list[WeatherAlert], bool]:
    """Compute weather alerts and whether free cancel is allowed.

    Returns (alerts, allows_free_cancel).
    """
    alerts: list[WeatherAlert] = []
    allows_free_cancel = False

    # Check government warnings (typhoon, rainstorm)
    for w in warnings:
        title = (w.get("title") or "").lower()
        if "typhoon" in title or "颱風" in title or "台风" in title:
            alerts.append(WeatherAlert(type="typhoon", severity="severe", message=t("weather.typhoon", lang)))
            allows_free_cancel = True
        if "rainstorm" in title or "暴雨" in title:
            alerts.append(WeatherAlert(type="rainstorm", severity="severe", message=t("weather.rainstorm", lang)))
            allows_free_cancel = True

    # Rain probability
    if rain_probability >= 80:
        alerts.append(WeatherAlert(type="rain", severity="severe", message=t("weather.rain_high", lang)))
        allows_free_cancel = True
    elif rain_probability >= 50:
        alerts.append(WeatherAlert(type="rain", severity="info", message=t("weather.rain_possible", lang)))

    # Temperature
    if temperature >= 38:
        alerts.append(WeatherAlert(type="heat", severity="severe", message=t("weather.heat_extreme", lang)))
        allows_free_cancel = True
    elif temperature >= 35:
        alerts.append(WeatherAlert(type="heat", severity="warning", message=t("weather.heat_warning", lang)))

    # UV index
    if uv_index >= 8:
        alerts.append(WeatherAlert(type="uv", severity="warning", message=t("weather.uv_warning", lang)))

    return alerts, allows_free_cancel


async def _fetch_qweather(path: str, params: dict) -> dict | None:
    """Call QWeather API. Returns parsed JSON or None on failure."""
    params["key"] = settings.qweather_api_key
    url = f"{settings.qweather_base_url}{path}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(2):
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == "200":
                    return data
                logger.warning("QWeather returned code %s for %s", data.get("code"), path)
                return None
            except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
                if attempt == 0:
                    logger.warning("QWeather retry after error: %s", e)
                    continue
                logger.error("QWeather failed after retry: %s", e)
                return None
            except Exception as e:
                logger.error("QWeather unexpected error: %s", e)
                return None
    return None


async def _fetch_warnings(lat: float, lon: float) -> list[dict]:
    """Fetch active weather warnings for coordinates."""
    location = f"{lon},{lat}"
    data = await _fetch_qweather("/v7/warning/now", {"location": location})
    if data is None:
        return []
    return data.get("warning", [])


async def _fetch_daily_forecast(lat: float, lon: float, query_date: date) -> dict | None:
    """Fetch 7-day daily forecast and extract the matching day."""
    location = f"{lon},{lat}"
    data = await _fetch_qweather("/v7/weather/7d", {"location": location})
    if data is None:
        return None
    date_str = query_date.isoformat()
    for day in data.get("daily", []):
        if day.get("fxDate") == date_str:
            return day
    return None


async def _fetch_hourly_forecast(lat: float, lon: float, query_time: time) -> dict | None:
    """Fetch 24h hourly forecast and find the closest matching hour."""
    location = f"{lon},{lat}"
    data = await _fetch_qweather("/v7/weather/24h", {"location": location})
    if data is None:
        return None
    target_hour = query_time.hour
    for hour_data in data.get("hourly", []):
        # fxTime format: "2026-04-20T14:00+08:00"
        fx_time_str = hour_data.get("fxTime", "")
        try:
            fx_hour = int(fx_time_str[11:13])
        except (ValueError, IndexError):
            continue
        if fx_hour == target_hour:
            return hour_data
    return None


def _parse_daily(day: dict) -> dict:
    """Extract normalized fields from a QWeather daily forecast entry."""
    return {
        "temperature": int(day.get("tempMax", 0)),
        "feels_like": int(day.get("tempMax", 0)),  # daily doesn't have feelsLike; use tempMax
        "humidity": int(day.get("humidity", 0)),
        "rain_probability": 0,  # daily forecast doesn't have precip probability; rely on warnings
        "wind_speed_kph": float(day.get("windSpeedDay", 0)),
        "uv_index": int(day.get("uvIndex", 0)),
        "condition": day.get("textDay", "unknown"),
        "condition_icon": day.get("iconDay", "unknown"),
    }


def _parse_hourly(hour: dict) -> dict:
    """Extract normalized fields from a QWeather hourly forecast entry."""
    return {
        "temperature": int(hour.get("temp", 0)),
        "feels_like": int(hour.get("feelsLike", hour.get("temp", 0))),
        "humidity": int(hour.get("humidity", 0)),
        "rain_probability": int(hour.get("pop", 0)),
        "wind_speed_kph": float(hour.get("windSpeed", 0)),
        "uv_index": 0,  # hourly doesn't have UV; will supplement from daily if available
        "condition": hour.get("text", "unknown"),
        "condition_icon": hour.get("icon", "unknown"),
    }


async def get_weather(
    lat: float,
    lon: float,
    query_date: date,
    query_time: time | None,
    court_id,
    lang: str = "zh-Hant",
) -> WeatherResponse | None:
    """Get weather for a location and date/time. Returns None only on total failure (no API, no cache)."""
    key = _cache_key(lat, lon, query_date, query_time)

    # Check cache
    cached = await redis_client.get(key)
    if cached:
        data = json.loads(cached)
        return WeatherResponse(**data)

    # Determine which forecast to use
    now = datetime.now(timezone.utc)
    target_dt = datetime.combine(query_date, query_time or time(12, 0), tzinfo=timezone.utc)
    hours_until = (target_dt - now).total_seconds() / 3600
    use_hourly = hours_until <= 24 and query_time is not None

    # Fetch weather data
    if use_hourly:
        forecast = await _fetch_hourly_forecast(lat, lon, query_time)
    else:
        forecast = await _fetch_daily_forecast(lat, lon, query_date)

    if forecast is None:
        return None

    # Parse fields
    if use_hourly:
        fields = _parse_hourly(forecast)
    else:
        fields = _parse_daily(forecast)

    # Fetch warnings
    warnings = await _fetch_warnings(lat, lon)

    # Compute alerts
    alerts, allows_free_cancel = _compute_alerts(
        temperature=fields["temperature"],
        rain_probability=fields["rain_probability"],
        uv_index=fields["uv_index"],
        warnings=warnings,
        lang=lang,
    )

    response = WeatherResponse(
        court_id=court_id,
        date=query_date,
        start_time=query_time,
        **fields,
        alerts=alerts,
        allows_free_cancel=allows_free_cancel,
    )

    # Cache result
    ttl = _cache_ttl(query_date)
    await redis_client.set(key, json.dumps(response.model_dump(mode="json")), ex=ttl)

    return response


async def check_free_cancel(
    lat: float,
    lon: float,
    play_date: date,
    start_time: time | None,
    court_id,
) -> bool:
    """Check if weather conditions allow penalty-free cancellation.

    Called from cancel_booking(). Uses cached weather if available.
    """
    result = await get_weather(lat, lon, play_date, start_time, court_id)
    if result is None:
        return False  # Can't verify weather → no free cancel
    return result.allows_free_cancel
