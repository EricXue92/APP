"""Boundary value tests for credit, scores, NTRP, and time overlaps."""
from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditReason
from app.models.user import AuthProvider
from app.services.credit import apply_credit_change
from app.services.user import create_user_with_auth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(session: AsyncSession, username: str, credit: int = 80, cancel_count: int = 0):
    user = await create_user_with_auth(
        session,
        nickname=username,
        gender="male",
        city="HK",
        ntrp_level="3.5",
        language="en",
        provider=AuthProvider.USERNAME,
        provider_user_id=username,
        password="pass1234",
    )
    user.credit_score = credit
    user.cancel_count = cancel_count
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Credit boundaries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_credit_at_zero_stays_zero(session: AsyncSession):
    user = await _make_user(session, "b_zero", credit=0, cancel_count=1)
    user = await apply_credit_change(session, user, CreditReason.NO_SHOW)
    assert user.credit_score == 0


@pytest.mark.asyncio
async def test_credit_at_100_stays_100(session: AsyncSession):
    user = await _make_user(session, "b_100", credit=100)
    user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 100


@pytest.mark.asyncio
async def test_credit_95_plus_5_becomes_100(session: AsyncSession):
    user = await _make_user(session, "b_95", credit=95)
    user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 100


# ---------------------------------------------------------------------------
# Score validation boundaries
# ---------------------------------------------------------------------------

from app.services.event import validate_set_score


def test_boundary_tiebreak_7_5():
    assert validate_set_score(7, 6, 7, 5, 6) is True


def test_boundary_tiebreak_7_4():
    """7-4 is valid (winner >=7, margin >=2)."""
    assert validate_set_score(7, 6, 7, 4, 6) is True


def test_boundary_tiebreak_7_3():
    assert validate_set_score(7, 6, 7, 3, 6) is True


def test_boundary_match_tiebreak_10_8():
    assert validate_set_score(1, 0, 10, 8, 6, is_match_tiebreak=True) is True


def test_boundary_match_tiebreak_11_9():
    assert validate_set_score(1, 0, 11, 9, 6, is_match_tiebreak=True) is True


def test_boundary_match_tiebreak_10_9_invalid():
    """10-9 violates win-by-2."""
    assert validate_set_score(1, 0, 10, 9, 6, is_match_tiebreak=True) is False


# ---------------------------------------------------------------------------
# NTRP boundary
# ---------------------------------------------------------------------------

from app.services.booking import _ntrp_to_float


def test_ntrp_to_float_basic():
    assert _ntrp_to_float("3.5") == 3.5


def test_ntrp_to_float_plus():
    assert _ntrp_to_float("3.5+") == 3.55


def test_ntrp_to_float_minus():
    assert _ntrp_to_float("3.5-") == 3.45


# ---------------------------------------------------------------------------
# Matching overlap boundaries
# ---------------------------------------------------------------------------

from app.services.matching import _time_overlap_minutes


def test_overlap_boundary_one_minute():
    assert _time_overlap_minutes(time(9, 0), time(10, 0), time(9, 59), time(11, 0)) == 1


def test_overlap_boundary_zero():
    assert _time_overlap_minutes(time(9, 0), time(10, 0), time(10, 0), time(11, 0)) == 0
