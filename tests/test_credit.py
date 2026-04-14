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
