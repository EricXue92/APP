import uuid

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models.follow import Follow
from app.models.user import User
from app.services.block import is_blocked


async def create_follow(
    session: AsyncSession,
    *,
    follower_id: uuid.UUID,
    followed_id: uuid.UUID,
    lang: str = "en",
) -> dict:
    if follower_id == followed_id:
        raise ValueError(t("follow.cannot_follow_self", lang))

    # Validate target user exists
    result = await session.execute(select(User).where(User.id == followed_id))
    if result.scalar_one_or_none() is None:
        raise ValueError(t("follow.user_not_found", lang))

    # Check block
    if await is_blocked(session, follower_id, followed_id):
        raise ValueError(t("follow.blocked", lang))

    # Check duplicate
    existing = await session.execute(
        select(Follow).where(Follow.follower_id == follower_id, Follow.followed_id == followed_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError(t("follow.already_following", lang))

    follow = Follow(follower_id=follower_id, followed_id=followed_id)
    session.add(follow)
    await session.commit()
    await session.refresh(follow)

    # Compute is_mutual
    mutual = await _check_reverse(session, follower_id, followed_id)

    return _to_dict(follow, mutual)


async def delete_follow(
    session: AsyncSession,
    *,
    follower_id: uuid.UUID,
    followed_id: uuid.UUID,
    lang: str = "en",
) -> None:
    result = await session.execute(
        select(Follow).where(Follow.follower_id == follower_id, Follow.followed_id == followed_id)
    )
    follow = result.scalar_one_or_none()
    if follow is None:
        raise LookupError(t("follow.not_found", lang))

    await session.delete(follow)
    await session.commit()


async def list_followers(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    result = await session.execute(
        select(Follow).where(Follow.followed_id == user_id).order_by(Follow.created_at.desc())
    )
    follows = list(result.scalars().all())
    return await _attach_mutual(session, follows)


async def list_following(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    result = await session.execute(
        select(Follow).where(Follow.follower_id == user_id).order_by(Follow.created_at.desc())
    )
    follows = list(result.scalars().all())
    return await _attach_mutual(session, follows)


async def is_mutual(session: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    """Check if both users follow each other."""
    result = await session.execute(
        select(Follow.id).where(Follow.follower_id == user_a, Follow.followed_id == user_b)
    )
    a_follows_b = result.scalar_one_or_none() is not None

    result = await session.execute(
        select(Follow.id).where(Follow.follower_id == user_b, Follow.followed_id == user_a)
    )
    b_follows_a = result.scalar_one_or_none() is not None

    return a_follows_b and b_follows_a


async def remove_follows_between(session: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> None:
    """Remove all follow relationships between two users (both directions)."""
    await session.execute(
        delete(Follow).where(
            or_(
                and_(Follow.follower_id == user_a, Follow.followed_id == user_b),
                and_(Follow.follower_id == user_b, Follow.followed_id == user_a),
            )
        )
    )


async def _check_reverse(session: AsyncSession, follower_id: uuid.UUID, followed_id: uuid.UUID) -> bool:
    """Check if the followed user also follows the follower."""
    result = await session.execute(
        select(Follow.id).where(Follow.follower_id == followed_id, Follow.followed_id == follower_id)
    )
    return result.scalar_one_or_none() is not None


async def _attach_mutual(session: AsyncSession, follows: list[Follow]) -> list[dict]:
    """Attach is_mutual to a list of Follow objects."""
    results = []
    for f in follows:
        mutual = await _check_reverse(session, f.follower_id, f.followed_id)
        results.append(_to_dict(f, mutual))
    return results


def _to_dict(follow: Follow, is_mutual: bool) -> dict:
    return {
        "id": follow.id,
        "follower_id": follow.follower_id,
        "followed_id": follow.followed_id,
        "is_mutual": is_mutual,
        "created_at": follow.created_at,
    }
