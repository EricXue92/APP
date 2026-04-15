import uuid
from datetime import date, time, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType


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


# ── Endpoint tests ──────────────────────────────────────────────────────


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

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)  # no cache hit
    mock_redis.set = AsyncMock(return_value=True)

    with (
        patch("app.services.weather._fetch_qweather") as mock_fetch,
        patch("app.services.weather.redis_client", mock_redis),
    ):
        mock_fetch.side_effect = [
            _mock_daily_response(),    # daily forecast
            _mock_warning_response_empty(),  # warnings
        ]

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


# ── Free cancel integration tests ──────────────────────────────────────


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


# ── check_free_cancel unit tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_free_cancel_returns_true():
    """check_free_cancel returns True when get_weather reports allows_free_cancel."""
    from app.services.weather import check_free_cancel
    from app.schemas.weather import WeatherResponse

    court_uuid = uuid.uuid4()
    mock_result = WeatherResponse(
        court_id=court_uuid,
        date=date.today() + timedelta(days=3),
        start_time=time(10, 0),
        temperature=25,
        feels_like=25,
        humidity=70,
        rain_probability=85,
        wind_speed_kph=10.0,
        uv_index=3,
        condition="rainy",
        condition_icon="rainy",
        alerts=[],
        allows_free_cancel=True,
    )

    with patch("app.services.weather.get_weather", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await check_free_cancel(
            lat=22.28,
            lon=114.17,
            play_date=date.today() + timedelta(days=3),
            start_time=time(10, 0),
            court_id=court_uuid,
        )

    assert result is True


@pytest.mark.asyncio
async def test_check_free_cancel_returns_false_no_alerts():
    """check_free_cancel returns False when weather is normal (no severe conditions)."""
    from app.services.weather import check_free_cancel
    from app.schemas.weather import WeatherResponse

    court_uuid = uuid.uuid4()
    mock_result = WeatherResponse(
        court_id=court_uuid,
        date=date.today() + timedelta(days=3),
        start_time=time(10, 0),
        temperature=25,
        feels_like=25,
        humidity=60,
        rain_probability=20,
        wind_speed_kph=8.0,
        uv_index=3,
        condition="sunny",
        condition_icon="sunny",
        alerts=[],
        allows_free_cancel=False,
    )

    with patch("app.services.weather.get_weather", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await check_free_cancel(
            lat=22.28,
            lon=114.17,
            play_date=date.today() + timedelta(days=3),
            start_time=time(10, 0),
            court_id=court_uuid,
        )

    assert result is False


@pytest.mark.asyncio
async def test_check_free_cancel_returns_false_when_weather_unavailable():
    """check_free_cancel returns False when get_weather returns None (API failure)."""
    from app.services.weather import check_free_cancel

    with patch("app.services.weather.get_weather", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        result = await check_free_cancel(
            lat=22.28,
            lon=114.17,
            play_date=date.today() + timedelta(days=3),
            start_time=time(10, 0),
            court_id=1,
        )

    assert result is False


# ── Cache hit path test ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_weather_cache_hit_skips_fetch():
    """When Redis returns cached data, _fetch_qweather should never be called."""
    from app.services.weather import get_weather
    from app.schemas.weather import WeatherResponse

    court_uuid = uuid.uuid4()
    cached_response = WeatherResponse(
        court_id=court_uuid,
        date=date.today() + timedelta(days=3),
        start_time=None,
        temperature=28,
        feels_like=28,
        humidity=65,
        rain_probability=10,
        wind_speed_kph=5.0,
        uv_index=4,
        condition="cloudy",
        condition_icon="cloudy",
        alerts=[],
        allows_free_cancel=False,
    )
    cached_json = cached_response.model_dump_json()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=cached_json)
    mock_redis.set = AsyncMock(return_value=True)

    with (
        patch("app.services.weather.redis_client", mock_redis),
        patch("app.services.weather._fetch_qweather") as mock_fetch,
    ):
        result = await get_weather(
            lat=22.28,
            lon=114.17,
            query_date=date.today() + timedelta(days=3),
            query_time=None,
            court_id=court_uuid,
        )

    mock_fetch.assert_not_called()
    assert result is not None
    assert result.temperature == 28
    assert result.allows_free_cancel is False


# ── Chinese typhoon alert variants ──────────────────────────────────────


def test_compute_alerts_traditional_chinese_typhoon():
    """_compute_alerts handles Traditional Chinese typhoon warning text '颱風'."""
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=20, uv_index=3,
        warnings=[{"title": "颱風信號八號"}], lang="zh-Hant",
    )
    assert free_cancel is True
    assert any(a.type == "typhoon" for a in alerts)


def test_compute_alerts_simplified_chinese_typhoon():
    """_compute_alerts handles Simplified Chinese typhoon warning text '台风'."""
    from app.services.weather import _compute_alerts

    alerts, free_cancel = _compute_alerts(
        temperature=25, rain_probability=20, uv_index=3,
        warnings=[{"title": "台风橙色预警"}], lang="zh-Hans",
    )
    assert free_cancel is True
    assert any(a.type == "typhoon" for a in alerts)
