import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import AuthProvider, Gender, User, UserAuth
from app.services.auth import generate_ntrp_label, hash_password


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_auth(session: AsyncSession, provider: AuthProvider, provider_user_id: str) -> UserAuth | None:
    result = await session.execute(
        select(UserAuth)
        .options(selectinload(UserAuth.user))
        .where(UserAuth.provider == provider, UserAuth.provider_user_id == provider_user_id)
    )
    return result.scalar_one_or_none()


async def create_user_with_auth(
    session: AsyncSession,
    *,
    nickname: str,
    gender: str,
    city: str,
    ntrp_level: str,
    language: str,
    provider: AuthProvider,
    provider_user_id: str,
    password: str | None = None,
    email: str | None = None,
) -> User:
    user = User(
        nickname=nickname,
        gender=Gender(gender),
        city=city,
        ntrp_level=ntrp_level,
        ntrp_label=generate_ntrp_label(ntrp_level),
        language=language,
    )
    session.add(user)
    await session.flush()

    auth = UserAuth(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        password_hash=hash_password(password) if password else None,
        email=email,
        email_verified=False,
    )
    session.add(auth)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, **kwargs) -> User:
    for key, value in kwargs.items():
        if value is not None:
            if key == "ntrp_level":
                setattr(user, "ntrp_label", generate_ntrp_label(value))
            setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return user
