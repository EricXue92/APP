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
