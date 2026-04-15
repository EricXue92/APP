# Weather Integration (天气集成) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate QWeather API to show weather conditions for bookings and allow penalty-free cancellation during severe weather.

**Architecture:** Standalone weather service (`services/weather.py`) with Redis caching, a single GET endpoint (`/api/v1/weather`), and one integration point in `cancel_booking()` for free-cancel verification. No new database models — weather data is ephemeral in Redis.

**Tech Stack:** FastAPI, httpx (async HTTP), Redis (caching), QWeather API, Pydantic v2

---

### Task 1: Config + Schemas

**Files:**
- Modify: `app/config.py`
- Create: `app/schemas/weather.py`

- [ ] **Step 1: Add QWeather config fields**

In `app/config.py`, add two fields to `Settings`:

```python
# QWeather (天气)
qweather_api_key: str = ""
qweather_base_url: str = "https://devapi.qweather.com"
```

Add them after the `assistant_rate_limit` line, before `model_config`.

- [ ] **Step 2: Create weather schemas**

Create `app/schemas/weather.py`:

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add app/config.py app/schemas/weather.py
git commit -m "feat(weather): add config fields and response schemas"
```

---

### Task 2: i18n — Weather Alert Messages

**Files:**
- Modify: `app/i18n.py`

- [ ] **Step 1: Add weather alert messages**

Add the following entries to `_MESSAGES` in `app/i18n.py`, after the `"matching.target_not_found"` entry:

```python
    "weather.typhoon": {
        "zh-Hans": "台风警告生效，建议取消",
        "zh-Hant": "颱風警告生效，建議取消",
        "en": "Typhoon warning active, consider cancelling",
    },
    "weather.rainstorm": {
        "zh-Hans": "暴雨警告生效，建议取消",
        "zh-Hant": "暴雨警告生效，建議取消",
        "en": "Heavy rainstorm warning active, consider cancelling",
    },
    "weather.rain_high": {
        "zh-Hans": "降雨概率极高，可免责取消",
        "zh-Hant": "降雨機率極高，可免責取消",
        "en": "Very high chance of rain, free cancellation available",
    },
    "weather.heat_extreme": {
        "zh-Hans": "极端高温，建议取消",
        "zh-Hant": "極端高溫，建議取消",
        "en": "Extreme heat, consider cancelling",
    },
    "weather.heat_warning": {
        "zh-Hans": "高温预警，建议选择早晚时段",
        "zh-Hant": "高溫預警，建議選擇早晚時段",
        "en": "High temperature warning, consider early or late hours",
    },
    "weather.uv_warning": {
        "zh-Hans": "紫外线强烈，请注意防晒",
        "zh-Hant": "紫外線強烈，請注意防曬",
        "en": "Strong UV, please wear sunscreen",
    },
    "weather.rain_possible": {
        "zh-Hans": "有降雨可能，建议携带雨具",
        "zh-Hant": "有降雨可能，建議攜帶雨具",
        "en": "Possible rain, consider bringing an umbrella",
    },
    "weather.court_no_coordinates": {
        "zh-Hans": "该球场缺少坐标信息",
        "zh-Hant": "該球場缺少坐標資訊",
        "en": "This court has no location coordinates",
    },
    "weather.date_out_of_range": {
        "zh-Hans": "日期必须在今天到未来7天之间",
        "zh-Hant": "日期必須在今天到未來7天之間",
        "en": "Date must be between today and 7 days from now",
    },
    "weather.service_unavailable": {
        "zh-Hans": "天气服务暂时不可用",
        "zh-Hant": "天氣服務暫時不可用",
        "en": "Weather service temporarily unavailable",
    },
```

- [ ] **Step 2: Commit**

```bash
git add app/i18n.py
git commit -m "feat(weather): add i18n messages for weather alerts"
```

---

### Task 3: Weather Service — QWeather Client + Caching

**Files:**
- Create: `app/services/weather.py`
- Create: `tests/test_weather.py` (start with unit tests)

- [ ] **Step 1: Write the failing test for `_round_coord` and `_cache_key`**

Create `tests/test_weather.py`:

```python
import uuid
from datetime import date, time

import pytest


def test_round_coord():
    from app.services.weather import _round_coord

    assert _round_coord(22.27846) == "22.28"
    assert _round_coord(114.17239) == "114.17"
    assert _round_coord(-33.8688) == "-33.87"
    assert _round_coord(0.0) == "0.00"


def test_cache_key_with_time():
    from app.services.weather import _cache_key

    key = _cache_key(22.28, 114.17, date(2026, 4, 20), time(14, 30))
    assert key == "weather:22.28:114.17:2026-04-20:12"


def test_cache_key_day_level():
    from app.services.weather import _cache_key

    key = _cache_key(22.28, 114.17, date(2026, 4, 20), None)
    assert key == "weather:22.28:114.17:2026-04-20:day"


def test_cache_key_time_blocks():
    from app.services.weather import _cache_key

    assert _cache_key(22.28, 114.17, date(2026, 4, 20), time(0, 0)).endswith(":0")
    assert _cache_key(22.28, 114.17, date(2026, 4, 20), time(2, 59)).endswith(":0")
    assert _cache_key(22.28, 114.17, date(2026, 4, 20), time(3, 0)).endswith(":3")
    assert _cache_key(22.28, 114.17, date(2026, 4, 20), time(5, 30)).endswith(":3")
    assert _cache_key(22.28, 114.17, date(2026, 4, 20), time(21, 0)).endswith(":21")
    assert _cache_key(22.28, 114.17, date(2026, 4, 20), time(23, 59)).endswith(":21")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_weather.py::test_round_coord -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.weather'`

- [ ] **Step 3: Write the weather service with helpers, QWeather client, caching, and alert logic**

Create `app/services/weather.py`:

```python
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
        # Try stale cache
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_weather.py -v -k "test_round_coord or test_cache_key"`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/weather.py tests/test_weather.py
git commit -m "feat(weather): add weather service with QWeather client, caching, and alert logic"
```

---

### Task 4: Alert Logic Tests

**Files:**
- Modify: `tests/test_weather.py`

- [ ] **Step 1: Write tests for `_compute_alerts`**

Add to `tests/test_weather.py`:

```python
def test_compute_alerts_typhoon():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=30, uv_index=3,
        warnings=[{"title": "Typhoon Signal No. 8"}], lang="en",
    )
    assert free_cancel is True
    assert any(a.type == "typhoon" for a in alerts)


def test_compute_alerts_rainstorm():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=30, uv_index=3,
        warnings=[{"title": "暴雨警告"}], lang="zh-Hant",
    )
    assert free_cancel is True
    assert any(a.type == "rainstorm" for a in alerts)


def test_compute_alerts_rain_80():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=80, uv_index=3,
        warnings=[], lang="en",
    )
    assert free_cancel is True
    assert any(a.type == "rain" and a.severity == "severe" for a in alerts)


def test_compute_alerts_rain_50():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=50, uv_index=3,
        warnings=[], lang="en",
    )
    assert free_cancel is False
    assert any(a.type == "rain" and a.severity == "info" for a in alerts)


def test_compute_alerts_extreme_heat():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=38, rain_probability=0, uv_index=3,
        warnings=[], lang="en",
    )
    assert free_cancel is True
    assert any(a.type == "heat" and a.severity == "severe" for a in alerts)


def test_compute_alerts_heat_warning():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=35, rain_probability=0, uv_index=3,
        warnings=[], lang="en",
    )
    assert free_cancel is False
    assert any(a.type == "heat" and a.severity == "warning" for a in alerts)


def test_compute_alerts_uv_high():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=0, uv_index=8,
        warnings=[], lang="en",
    )
    assert free_cancel is False
    assert any(a.type == "uv" and a.severity == "warning" for a in alerts)


def test_compute_alerts_no_alerts():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=20, uv_index=3,
        warnings=[], lang="en",
    )
    assert free_cancel is False
    assert len(alerts) == 0


def test_compute_alerts_multiple():
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=38, rain_probability=85, uv_index=9,
        warnings=[], lang="en",
    )
    assert free_cancel is True
    types = {a.type for a in alerts}
    assert types == {"rain", "heat", "uv"}


def test_cache_ttl_tomorrow():
    from app.services.weather import _cache_ttl
    from datetime import date, timedelta

    ttl = _cache_ttl(date.today() + timedelta(days=1))
    assert ttl == 1800  # 30 min


def test_cache_ttl_3_days():
    from app.services.weather import _cache_ttl
    from datetime import date, timedelta

    ttl = _cache_ttl(date.today() + timedelta(days=2))
    assert ttl == 3600  # 1 hour


def test_cache_ttl_5_days():
    from app.services.weather import _cache_ttl
    from datetime import date, timedelta

    ttl = _cache_ttl(date.today() + timedelta(days=5))
    assert ttl == 10800  # 3 hours
```

- [ ] **Step 2: Run all weather tests**

Run: `uv run pytest tests/test_weather.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_weather.py
git commit -m "test(weather): add alert logic and cache TTL unit tests"
```

---

### Task 5: Weather Router

**Files:**
- Create: `app/routers/weather.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing test for the endpoint**

Add to `tests/test_weather.py`:

```python
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from app.models.court import Court, CourtType


async def _register_and_get_token(client: AsyncClient, username: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


async def _seed_court_with_coords(session: AsyncSession) -> Court:
    court = Court(
        name="Victoria Park Tennis",
        address="Victoria Park, Causeway Bay",
        city="Hong Kong",
        latitude=22.2820,
        longitude=114.1880,
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


def _mock_daily_response():
    future_date = (date.today() + timedelta(days=3)).isoformat()
    return {
        "code": "200",
        "daily": [
            {
                "fxDate": future_date,
                "tempMax": "30",
                "humidity": "70",
                "windSpeedDay": "12",
                "uvIndex": "6",
                "textDay": "partly_cloudy",
                "iconDay": "partly_cloudy",
            }
        ],
    }


def _mock_warning_response_empty():
    return {"code": "200", "warning": []}


@pytest.mark.asyncio
async def test_weather_endpoint_success(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "weather_user1")
    court = await _seed_court_with_coords(session)
    future_date = (date.today() + timedelta(days=3)).isoformat()

    with patch("app.services.weather._fetch_qweather") as mock_fetch:
        mock_fetch.side_effect = [
            _mock_daily_response(),    # daily forecast
            _mock_warning_response_empty(),  # warnings
        ]
        # Clear any cached data
        from app.redis import redis_client
        keys = await redis_client.keys("weather:*")
        for k in keys:
            await redis_client.delete(k)

        resp = await client.get(
            "/api/v1/weather",
            headers={"Authorization": f"Bearer {token}"},
            params={"court_id": str(court.id), "date": future_date},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["court_id"] == str(court.id)
    assert data["temperature"] == 30
    assert data["allows_free_cancel"] is False


@pytest.mark.asyncio
async def test_weather_endpoint_court_not_found(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "weather_user2")
    future_date = (date.today() + timedelta(days=3)).isoformat()
    fake_id = str(uuid.uuid4())

    resp = await client.get(
        "/api/v1/weather",
        headers={"Authorization": f"Bearer {token}"},
        params={"court_id": fake_id, "date": future_date},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_weather_endpoint_no_coordinates(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "weather_user3")
    court = Court(
        name="No Coords Court",
        address="Somewhere",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)

    future_date = (date.today() + timedelta(days=3)).isoformat()
    resp = await client.get(
        "/api/v1/weather",
        headers={"Authorization": f"Bearer {token}"},
        params={"court_id": str(court.id), "date": future_date},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_weather_endpoint_date_in_past(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "weather_user4")
    court = await _seed_court_with_coords(session)
    past_date = (date.today() - timedelta(days=1)).isoformat()

    resp = await client.get(
        "/api/v1/weather",
        headers={"Authorization": f"Bearer {token}"},
        params={"court_id": str(court.id), "date": past_date},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_weather_endpoint_date_too_far(client: AsyncClient, session: AsyncSession):
    token, _ = await _register_and_get_token(client, "weather_user5")
    court = await _seed_court_with_coords(session)
    far_date = (date.today() + timedelta(days=8)).isoformat()

    resp = await client.get(
        "/api/v1/weather",
        headers={"Authorization": f"Bearer {token}"},
        params={"court_id": str(court.id), "date": far_date},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_weather.py::test_weather_endpoint_success -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Create the weather router**

Create `app/routers/weather.py`:

```python
import uuid
from datetime import date as date_cls
from datetime import time

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.weather import WeatherResponse
from app.services.court import get_court_by_id
from app.services.weather import get_weather

router = APIRouter()


@router.get("", response_model=WeatherResponse)
async def get_weather_for_court(
    session: DbSession,
    user: CurrentUser,
    lang: Lang,
    court_id: uuid.UUID = Query(...),
    query_date: date_cls = Query(..., alias="date"),
    start_time: time | None = Query(default=None),
):
    court = await get_court_by_id(session, court_id)
    if court is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))

    if court.latitude is None or court.longitude is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("weather.court_no_coordinates", lang))

    diff_days = (query_date - date_cls.today()).days
    if diff_days < 0 or diff_days > 7:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("weather.date_out_of_range", lang))

    result = await get_weather(
        lat=court.latitude,
        lon=court.longitude,
        query_date=query_date,
        query_time=start_time,
        court_id=court.id,
        lang=lang,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=t("weather.service_unavailable", lang))

    return result
```

- [ ] **Step 4: Register the router in `app/main.py`**

Add to the imports in `create_app()`:

```python
from app.routers import auth, assistant, blocks, bookings, courts, follows, matching, notifications, reports, reviews, users, weather
```

Add after the reports admin router line:

```python
app.include_router(weather.router, prefix="/api/v1/weather", tags=["weather"])
```

- [ ] **Step 5: Run endpoint tests**

Run: `uv run pytest tests/test_weather.py -v -k "test_weather_endpoint"`
Expected: All 5 endpoint tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/weather.py app/main.py tests/test_weather.py
git commit -m "feat(weather): add GET /api/v1/weather endpoint with validation"
```

---

### Task 6: Free Cancel Integration in Booking Cancellation

**Files:**
- Modify: `app/services/booking.py`
- Modify: `tests/test_weather.py`

- [ ] **Step 1: Write the failing test for weather-based free cancel**

Add to `tests/test_weather.py`:

```python
@pytest.mark.asyncio
async def test_cancel_booking_free_cancel_weather(client: AsyncClient, session: AsyncSession):
    """When weather allows free cancel, credit should not be deducted."""
    token, user_id = await _register_and_get_token(client, "weather_cancel1")
    court = await _seed_court_with_coords(session)
    future_date = (date.today() + timedelta(days=3)).isoformat()

    # Create a booking
    create_resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": future_date,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
        },
    )
    assert create_resp.status_code == 201
    booking_id = create_resp.json()["id"]

    # Get initial credit score
    user_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    initial_credit = user_resp.json()["credit_score"]

    # Mock weather to allow free cancel (typhoon)
    with patch("app.services.booking.check_free_cancel", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True

        cancel_resp = await client.post(
            f"/api/v1/bookings/{booking_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Credit should remain the same
    user_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert user_resp.json()["credit_score"] == initial_credit


@pytest.mark.asyncio
async def test_cancel_booking_no_free_cancel(client: AsyncClient, session: AsyncSession):
    """When weather does not allow free cancel, normal penalty applies."""
    token, user_id = await _register_and_get_token(client, "weather_cancel2")
    court = await _seed_court_with_coords(session)
    future_date = (date.today() + timedelta(days=3)).isoformat()

    create_resp = await client.post(
        "/api/v1/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": future_date,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
            "gender_requirement": "any",
        },
    )
    assert create_resp.status_code == 201
    booking_id = create_resp.json()["id"]

    with patch("app.services.booking.check_free_cancel", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False

        cancel_resp = await client.post(
            f"/api/v1/bookings/{booking_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    # First cancel is always warning-only, so credit should still be the same,
    # but cancel_count should have incremented (verified by subsequent cancel behavior)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_weather.py::test_cancel_booking_free_cancel_weather -v`
Expected: FAIL — `check_free_cancel` not imported in `booking.py`

- [ ] **Step 3: Modify `cancel_booking()` to check weather**

In `app/services/booking.py`, add the import at the top:

```python
from app.services.weather import check_free_cancel
```

Replace the `cancel_booking` function with:

```python
async def cancel_booking(session: AsyncSession, booking: Booking, user: User) -> Booking:
    """Cancel a booking. If user is creator, cancels the whole booking. Otherwise cancels their participation."""
    play_dt = datetime.combine(booking.play_date, booking.start_time, tzinfo=timezone.utc)

    # Check if weather allows penalty-free cancellation
    court = booking.court or await session.get(Court, booking.court_id)
    weather_free = False
    if court and court.latitude is not None and court.longitude is not None:
        weather_free = await check_free_cancel(
            lat=court.latitude,
            lon=court.longitude,
            play_date=booking.play_date,
            start_time=booking.start_time,
            court_id=booking.court_id,
        )

    if weather_free:
        cancel_reason = CreditReason.WEATHER_CANCEL
    else:
        cancel_reason = _get_cancel_reason(play_dt)

    if user.id == booking.creator_id:
        booking.status = BookingStatus.CANCELLED
        # Notify all accepted/pending participants (except creator)
        for p in booking.participants:
            if p.user_id != user.id and p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
                await create_notification(
                    session,
                    recipient_id=p.user_id,
                    type=NotificationType.BOOKING_CANCELLED,
                    actor_id=user.id,
                    target_type="booking",
                    target_id=booking.id,
                )
        await apply_credit_change(session, user, cancel_reason, description=f"Cancelled booking {booking.id}")
    else:
        for p in booking.participants:
            if p.user_id == user.id and p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
                p.status = ParticipantStatus.CANCELLED
                break
        await apply_credit_change(session, user, cancel_reason, description=f"Withdrew from booking {booking.id}")

    await session.commit()
    await session.refresh(booking)
    return booking
```

Note: `WEATHER_CANCEL` is already in `_DELTAS` with delta `0` and is NOT in `_CANCEL_REASONS`, so `cancel_count` won't increment and no credit will be deducted.

- [ ] **Step 4: Run the free cancel tests**

Run: `uv run pytest tests/test_weather.py -v -k "test_cancel_booking"`
Expected: Both tests PASS

- [ ] **Step 5: Run ALL existing booking tests to ensure no regressions**

Run: `uv run pytest tests/test_bookings.py -v`
Expected: All existing booking tests PASS (the mock only activates in weather tests)

- [ ] **Step 6: Commit**

```bash
git add app/services/booking.py tests/test_weather.py
git commit -m "feat(weather): integrate free cancel check into booking cancellation"
```

---

### Task 7: Full Test Suite Run + CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Update CLAUDE.md with weather module documentation**

In the modules table in `CLAUDE.md`, add a new row after the Smart Matching entry:

```
| Weather (天气) | `weather.py` | QWeather API integration. GPS-coordinate weather. Redis cache with TTL by date proximity. Alert thresholds trigger `allows_free_cancel`. `check_free_cancel()` called from `cancel_booking()`. |
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with weather integration module"
```
