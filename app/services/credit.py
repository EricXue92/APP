import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditLog, CreditReason
from app.models.user import User

_DELTAS = {
    CreditReason.ATTENDED: 5,
    CreditReason.FIRST_CANCEL_WARNING: 0,
    CreditReason.CANCEL_24H: -1,
    CreditReason.CANCEL_12_24H: -2,
    CreditReason.CANCEL_2H: -5,
    CreditReason.NO_SHOW: -5,
    CreditReason.WEATHER_CANCEL: 0,
}

_CANCEL_REASONS = {
    CreditReason.CANCEL_24H,
    CreditReason.CANCEL_12_24H,
    CreditReason.CANCEL_2H,
    CreditReason.NO_SHOW,
}


async def apply_credit_change(session: AsyncSession, user: User, reason: CreditReason, description: str | None = None) -> User:
    delta = _DELTAS.get(reason, 0)
    actual_reason = reason

    if reason in _CANCEL_REASONS:
        if user.cancel_count == 0:
            delta = 0
            actual_reason = CreditReason.FIRST_CANCEL_WARNING
        user.cancel_count += 1

    new_score = max(0, min(100, user.credit_score + delta))
    user.credit_score = new_score

    log = CreditLog(
        user_id=user.id,
        delta=delta,
        reason=actual_reason,
        description=description,
    )
    session.add(log)
    await session.commit()
    await session.refresh(user)
    return user


async def get_credit_history(session: AsyncSession, user_id: uuid.UUID, limit: int = 50) -> list[CreditLog]:
    result = await session.execute(
        select(CreditLog)
        .where(CreditLog.user_id == user_id)
        .order_by(CreditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
