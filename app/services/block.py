import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models.block import Block
from app.models.review import Review
from app.models.user import User


async def create_block(
    session: AsyncSession,
    *,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
    lang: str = "en",
) -> Block:
    if blocker_id == blocked_id:
        raise ValueError(t("block.cannot_block_self", lang))

    # Validate blocked user exists
    result = await session.execute(select(User).where(User.id == blocked_id))
    if result.scalar_one_or_none() is None:
        raise ValueError(t("block.user_not_found", lang))

    # Check duplicate
    existing = await session.execute(
        select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError(t("block.already_blocked", lang))

    # Remove existing follows between the two users
    from app.services.follow import remove_follows_between  # deferred to avoid circular import
    await remove_follows_between(session, blocker_id, blocked_id)

    # Expire pending proposals between the two users
    from app.services.match_proposal import expire_proposals_on_block
    await expire_proposals_on_block(session, blocker_id, blocked_id)

    block = Block(blocker_id=blocker_id, blocked_id=blocked_id)
    session.add(block)

    # Hide mutual reviews
    result = await session.execute(
        select(Review).where(
            or_(
                and_(Review.reviewer_id == blocker_id, Review.reviewee_id == blocked_id),
                and_(Review.reviewer_id == blocked_id, Review.reviewee_id == blocker_id),
            ),
            Review.is_hidden == False,  # noqa: E712
        )
    )
    for review in result.scalars().all():
        review.is_hidden = True

    await session.commit()
    await session.refresh(block)
    return block


async def delete_block(
    session: AsyncSession,
    *,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
    lang: str = "en",
) -> None:
    result = await session.execute(
        select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
    )
    block = result.scalar_one_or_none()
    if block is None:
        raise LookupError(t("block.not_found", lang))

    await session.delete(block)
    await session.commit()


async def list_blocks(session: AsyncSession, blocker_id: uuid.UUID) -> list[Block]:
    result = await session.execute(
        select(Block).where(Block.blocker_id == blocker_id).order_by(Block.created_at.desc())
    )
    return list(result.scalars().all())


async def is_blocked(session: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    """Check if either user has blocked the other."""
    result = await session.execute(
        select(Block.id).where(
            or_(
                and_(Block.blocker_id == user_a, Block.blocked_id == user_b),
                and_(Block.blocker_id == user_b, Block.blocked_id == user_a),
            )
        )
    )
    return result.scalar_one_or_none() is not None
