# Weather Integration (天气集成) Design Spec

## Overview

Integrate weather data into the booking experience using QWeather (和风天气) API. Users see weather conditions for upcoming bookings and can cancel without credit penalty when severe weather is detected.

**Scope:** Backend only — standalone weather endpoint, Redis caching, free-cancel verification in booking cancellation flow.

---

## 1. Weather Endpoint

### `GET /api/v1/weather` (authenticated)

Query parameters:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `court_id` | UUID | Yes | Court to get weather for (uses court's GPS coordinates) |
| `date` | YYYY-MM-DD | Yes | Date to query |
| `start_time` | HH:MM | No | Specific hour; omit for day-level forecast |

Response:

```json
{
  "court_id": "uuid",
  "date": "2026-04-20",
  "start_time": "14:00",
  "temperature": 28,
  "feels_like": 31,
  "humidity": 75,
  "rain_probability": 60,
  "wind_speed_kph": 15,
  "uv_index": 6,
  "condition": "partly_cloudy",
  "condition_icon": "partly_cloudy",
  "alerts": [
    {
      "type": "rain",
      "severity": "warning",
      "message": "降雨機率 60%，建議攜帶雨具"
    }
  ],
  "allows_free_cancel": false
}
```

**Coordinate source:** Court model's `latitude` and `longitude` fields, passed directly to QWeather API as `location=longitude,latitude`. This gives accurate weather for courts in large cities where weather varies by district.

**Error handling:**
- Court not found → 404
- Court has no coordinates → 400 with message suggesting admin update
- QWeather API failure → 503 with fallback message (no cached data available) or return stale cache if available
- Date in the past or >7 days out → 400

---

## 2. Alert Thresholds

| Condition | `allows_free_cancel` | Alert severity | Message (zh-Hant) |
|-----------|---------------------|----------------|-------------------|
| Typhoon signal active | `true` | `severe` | 颱風警告生效，建議取消 |
| Heavy rainstorm warning | `true` | `severe` | 暴雨警告生效，建議取消 |
| Rain probability ≥ 80% | `true` | `severe` | 降雨機率極高，可免責取消 |
| Temperature ≥ 38°C | `true` | `severe` | 極端高溫，建議取消 |
| Temperature ≥ 35°C | `false` | `warning` | 高溫預警，建議選擇早晚時段 |
| UV index ≥ 8 | `false` | `warning` | 紫外線強烈，請注意防曬 |
| Rain probability ≥ 50% | `false` | `info` | 有降雨可能，建議攜帶雨具 |

Multiple alerts can be returned simultaneously (e.g., high temp + high UV).

---

## 3. Free Cancel Integration

**Location:** `services/booking.py → cancel_booking()`

**Logic:** Before calculating credit penalty, call `weather.check_free_cancel(session, court_id, play_date, start_time)`. If it returns `True`:
- Skip credit penalty entirely
- Use `CreditReason.WEATHER_CANCEL` (already exists in the enum) for the credit log
- Log with zero point change as record

**The check is server-side at cancel time** — no client trust. The user presses cancel, the server fetches/checks weather, and decides whether to waive the penalty.

---

## 4. QWeather API Integration

### API endpoints used

| QWeather Endpoint | When used |
|-------------------|-----------|
| 7-day daily forecast (`/v7/weather/7d`) | Bookings 1-7 days out, or when no `start_time` |
| 24-hour hourly forecast (`/v7/weather/24h`) | Bookings within 24 hours with `start_time` |
| Weather warning (`/v7/warning/now`) | Check for active typhoon/rainstorm signals |

### Request format

All endpoints accept `location=longitude,latitude` (decimal, comma-separated).

### Client

- `httpx.AsyncClient` for async HTTP calls
- Timeout: 5 seconds
- Retry: 1 retry on timeout/5xx

---

## 5. Redis Caching

**Key format:** `weather:{lat_2dp}:{lon_2dp}:{date}:{hour_block}`

- Coordinates rounded to 2 decimal places (~1.1km grid) — nearby courts share cache
- `hour_block`: 3-hour blocks (0, 3, 6, 9, 12, 15, 18, 21) matching QWeather granularity
- Day-level queries use key `weather:{lat_2dp}:{lon_2dp}:{date}:day`

**TTL strategy:**

| Time until booking | TTL |
|-------------------|-----|
| ≤ 24 hours | 30 minutes |
| 1-3 days | 1 hour |
| 3-7 days | 3 hours |

**Cache miss:** Fetch from QWeather, compute alerts, store result, return.

**Cache structure:** Store the full response JSON (already computed alerts and `allows_free_cancel`).

**Stale cache on API failure:** If QWeather returns an error and a stale cache entry exists, return the stale data with a flag `"weather_data_stale": true`. If no cache at all, return 503.

---

## 6. New Files

| File | Purpose |
|------|---------|
| `app/services/weather.py` | QWeather client, Redis caching, alert computation, `check_free_cancel()` |
| `app/routers/weather.py` | `GET /api/v1/weather` endpoint |
| `app/schemas/weather.py` | `WeatherQuery` (query params), `WeatherAlert`, `WeatherResponse` |
| `tests/test_weather.py` | Tests with mocked QWeather responses |

## 7. Modified Files

| File | Change |
|------|--------|
| `app/config.py` | Add `qweather_api_key: str`, `qweather_base_url: str` |
| `app/main.py` | Register weather router |
| `app/services/booking.py` | Call `check_free_cancel()` in `cancel_booking()`, skip penalty if `True` |
| `app/i18n.py` | Weather alert messages in zh-Hant, zh-Hans, en |

## 8. No New Models

No database tables needed. Weather data is ephemeral — Redis cache only. The `CreditReason.WEATHER_CANCEL` enum value already exists.

## 9. Not Included

- No push notifications for weather warnings — iOS polls the weather endpoint
- No weather history storage
- No background scheduled weather checks
- No indoor court exemption (could add later — indoor courts wouldn't need weather warnings)
