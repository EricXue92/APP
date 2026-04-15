import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.services.auth import decode_token
from app.services.user import get_user_by_id

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: DbSession,
    authorization: str = Header(...),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = await get_user_by_id(session, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled")

    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been suspended")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_language(accept_language: str = Header(default="zh-Hant")) -> str:
    supported = {"zh-Hans", "zh-Hant", "en"}
    if accept_language in supported:
        return accept_language
    return "zh-Hant"


Lang = Annotated[str, Depends(get_language)]


from app.models.user import UserRole


async def require_admin(user: CurrentUser) -> User:
    if user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def require_superadmin(user: CurrentUser) -> User:
    if user.role != UserRole.SUPERADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required")
    return user


SuperAdminUser = Annotated[User, Depends(require_superadmin)]
