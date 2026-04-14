from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import DbSession, Lang
from app.i18n import t
from app.models.user import AuthProvider
from app.schemas.auth import (
    PhoneLoginRequest,
    RefreshTokenRequest,
    RegisterProfileRequest,
    TokenResponse,
    UsernameLoginRequest,
    UsernameRegisterRequest,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.services.user import create_user_with_auth, get_user_auth

router = APIRouter()


@router.post("/register/username", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_with_username(
    body: UsernameRegisterRequest,
    profile: RegisterProfileRequest = Depends(),
    session: DbSession = None,
    lang: Lang = None,
):
    existing = await get_user_auth(session, AuthProvider.USERNAME, body.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=t("auth.provider_already_linked", lang))

    user = await create_user_with_auth(
        session,
        nickname=profile.nickname,
        gender=profile.gender,
        city=profile.city,
        ntrp_level=profile.ntrp_level,
        language=profile.language,
        provider=AuthProvider.USERNAME,
        provider_user_id=body.username,
        password=body.password,
        email=body.email,
    )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user_id=user.id)


@router.post("/login/username", response_model=TokenResponse)
async def login_with_username(body: UsernameLoginRequest, session: DbSession, lang: Lang):
    auth = await get_user_auth(session, AuthProvider.USERNAME, body.username)
    if auth is None or auth.password_hash is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.invalid_credentials", lang))

    if not verify_password(body.password, auth.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.invalid_credentials", lang))

    if not auth.user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("auth.account_disabled", lang))

    access_token = create_access_token(str(auth.user_id))
    refresh_token = create_refresh_token(str(auth.user_id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user_id=auth.user_id)


@router.post("/login/phone", response_model=TokenResponse)
async def login_with_phone(body: PhoneLoginRequest, session: DbSession, lang: Lang):
    # MVP: accept code "000000" in development mode
    if body.code != "000000":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.phone_code_invalid", lang))

    auth = await get_user_auth(session, AuthProvider.PHONE, body.phone)
    if auth is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("auth.user_not_found", lang))

    if not auth.user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("auth.account_disabled", lang))

    access_token = create_access_token(str(auth.user_id))
    refresh_token = create_refresh_token(str(auth.user_id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user_id=auth.user_id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshTokenRequest, session: DbSession, lang: Lang):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.invalid_credentials", lang))

    user_id = payload.get("sub")
    import uuid
    from app.services.user import get_user_by_id
    user = await get_user_by_id(session, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.user_not_found", lang))

    access_token = create_access_token(str(user.id))
    new_refresh = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=new_refresh, user_id=user.id)
