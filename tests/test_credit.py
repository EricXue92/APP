import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditReason
from app.models.user import AuthProvider
from app.services.credit import apply_credit_change, get_credit_history
from app.services.user import create_user_with_auth


async def _create_test_user(session: AsyncSession, username: str = "credituser"):
    user = await create_user_with_auth(
        session,
        nickname="CreditTest",
        gender="male",
        city="Hong Kong",
        ntrp_level="3.5",
        language="en",
        provider=AuthProvider.USERNAME,
        provider_user_id=username,
        password="test1234",
    )
    return user


@pytest.mark.asyncio
async def test_attend_increases_credit(session):
    user = await _create_test_user(session, "attend1")
    assert user.credit_score == 80
    user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 85


@pytest.mark.asyncio
async def test_credit_max_100(session):
    user = await _create_test_user(session, "max100")
    user.credit_score = 98
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 100


@pytest.mark.asyncio
async def test_first_cancel_no_deduction(session):
    user = await _create_test_user(session, "firstcancel")
    assert user.cancel_count == 0
    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 80
    assert user.cancel_count == 1


@pytest.mark.asyncio
async def test_second_cancel_deducts(session):
    user = await _create_test_user(session, "secondcancel")
    user.cancel_count = 1
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 79
    assert user.cancel_count == 2


@pytest.mark.asyncio
async def test_no_show_deducts_5(session):
    user = await _create_test_user(session, "noshow1")
    user.cancel_count = 1
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.NO_SHOW)
    assert user.credit_score == 75


@pytest.mark.asyncio
async def test_weather_cancel_no_deduction(session):
    user = await _create_test_user(session, "weather1")
    user = await apply_credit_change(session, user, CreditReason.WEATHER_CANCEL)
    assert user.credit_score == 80


@pytest.mark.asyncio
async def test_credit_history(session):
    user = await _create_test_user(session, "history1")
    await apply_credit_change(session, user, CreditReason.ATTENDED)
    await apply_credit_change(session, user, CreditReason.ATTENDED)
    logs = await get_credit_history(session, user.id)
    assert len(logs) == 2
    assert all(log.delta == 5 for log in logs)


@pytest.mark.asyncio
async def test_cancel_12_24h_deducts_2(session):
    user = await _create_test_user(session, "cancel12_24h")
    user.cancel_count = 1
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.CANCEL_12_24H)
    assert user.credit_score == 78
    assert user.cancel_count == 2


@pytest.mark.asyncio
async def test_cancel_2h_deducts_5(session):
    user = await _create_test_user(session, "cancel2h")
    user.cancel_count = 1
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.CANCEL_2H)
    assert user.credit_score == 75
    assert user.cancel_count == 2


@pytest.mark.asyncio
async def test_credit_floor_at_zero(session):
    """Credit score should never go below 0."""
    user = await _create_test_user(session, "floor0")
    user.credit_score = 2
    user.cancel_count = 1
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.NO_SHOW)
    assert user.credit_score == 0


@pytest.mark.asyncio
async def test_admin_adjust_zero_delta(session):
    """ADMIN_ADJUST is not in _DELTAS so delta defaults to 0."""
    user = await _create_test_user(session, "adminadj")
    user = await apply_credit_change(session, user, CreditReason.ADMIN_ADJUST)
    assert user.credit_score == 80


@pytest.mark.asyncio
async def test_three_consecutive_cancels(session):
    """Third cancel should still apply full penalty."""
    user = await _create_test_user(session, "threecancel")
    # 1st cancel: warning
    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 80 and user.cancel_count == 1
    # 2nd cancel: -1
    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 79 and user.cancel_count == 2
    # 3rd cancel: -1
    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 78 and user.cancel_count == 3


@pytest.mark.asyncio
async def test_credit_log_description(session):
    """Description should be stored in CreditLog."""
    user = await _create_test_user(session, "logdesc")
    await apply_credit_change(session, user, CreditReason.ATTENDED, description="Booking #123")
    logs = await get_credit_history(session, user.id)
    assert len(logs) == 1
    assert logs[0].description == "Booking #123"


@pytest.mark.asyncio
async def test_credit_history_empty(session):
    user = await _create_test_user(session, "nologs")
    logs = await get_credit_history(session, user.id)
    assert logs == []


@pytest.mark.asyncio
async def test_credit_history_custom_limit(session):
    user = await _create_test_user(session, "limitlog")
    for _ in range(5):
        await apply_credit_change(session, user, CreditReason.ATTENDED)
    logs = await get_credit_history(session, user.id, limit=3)
    assert len(logs) == 3


# --- Edge Case: Multiple attends capped at 100 ---

@pytest.mark.asyncio
async def test_attend_many_times_capped_at_100(session):
    """Attending many times should cap credit at 100, never exceed."""
    user = await _create_test_user(session, "manycap")
    for _ in range(10):
        user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 100


# --- Edge Case: Heavy penalty from low score stays at 0 ---

@pytest.mark.asyncio
async def test_multiple_noshow_floors_at_zero(session):
    """Multiple no-shows from a low score should stay at 0, not go negative."""
    user = await _create_test_user(session, "multinoshow")
    user.credit_score = 3
    user.cancel_count = 1
    await session.commit()
    user = await apply_credit_change(session, user, CreditReason.NO_SHOW)
    assert user.credit_score == 0
    user = await apply_credit_change(session, user, CreditReason.NO_SHOW)
    assert user.credit_score == 0


# --- Edge Case: First cancel for each cancel type is warning ---

@pytest.mark.asyncio
async def test_first_cancel_warning_regardless_of_tier(session):
    """First cancel is always a warning, regardless of the cancel tier."""
    user = await _create_test_user(session, "firsttier")
    assert user.cancel_count == 0
    # Even a harsh CANCEL_2H is forgiven on first cancel
    user = await apply_credit_change(session, user, CreditReason.CANCEL_2H)
    assert user.credit_score == 80
    assert user.cancel_count == 1
