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
