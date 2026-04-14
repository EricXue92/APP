import uuid

from pydantic import BaseModel, EmailStr, Field


class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+?\d{8,15}$")
    code: str = Field(..., min_length=4, max_length=6)


class UsernameRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    email: EmailStr


class UsernameLoginRequest(BaseModel):
    username: str
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class WeChatLoginRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RegisterProfileRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)
    gender: str = Field(..., pattern=r"^(male|female)$")
    city: str = Field(..., min_length=1, max_length=50)
    ntrp_level: str = Field(..., pattern=r"^\d\.\d[+-]?$")
    language: str = Field(default="zh-Hant", pattern=r"^(zh-Hans|zh-Hant|en)$")
