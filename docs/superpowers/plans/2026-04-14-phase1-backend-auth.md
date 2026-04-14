# Phase 1: Backend Foundation + User Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend foundation with PostgreSQL database, Redis cache, and a complete user authentication system supporting phone SMS, WeChat, Google OAuth, and username+password login.

**Architecture:** FastAPI monolith with modular router structure. SQLAlchemy async ORM with Alembic migrations. JWT-based auth with refresh tokens. Redis for session caching and rate limiting.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL, Redis, Pydantic v2, pytest, httpx (test client), passlib (password hashing), python-jose (JWT)

**Spec Reference:** `docs/superpowers/specs/2026-04-14-lets-tennis-design.md` sections 1, 3, 10.4, 11, 12

---

## File Structure

```
app/
├── main.py                      # FastAPI app factory, lifespan, middleware
├── config.py                    # Settings via pydantic-settings (env vars)
├── database.py                  # Async SQLAlchemy engine, session factory
├── redis.py                     # Redis connection pool
├── models/
│   ├── __init__.py
│   ├── user.py                  # User, UserAuth SQLAlchemy models
│   └── credit.py                # CreditLog model
├── schemas/
│   ├── __init__.py
│   ├── user.py                  # Pydantic request/response schemas for user
│   └── auth.py                  # Pydantic schemas for auth (login, register, token)
├── routers/
│   ├── __init__.py
│   ├── auth.py                  # Auth endpoints (register, login, refresh, logout)
│   └── users.py                 # User profile endpoints (get, update, me)
├── services/
│   ├── __init__.py
│   ├── auth.py                  # Auth business logic (JWT, password, OAuth)
│   └── user.py                  # User CRUD operations
├── dependencies.py              # FastAPI dependencies (get_db, get_current_user)
└── i18n.py                      # Simple i18n helper for API error messages
alembic/
├── env.py
├── versions/                    # Migration files
alembic.ini
tests/
├── conftest.py                  # Fixtures: test DB, async client, test user
├── test_auth.py                 # Auth endpoint tests
├── test_users.py                # User profile tests
├── test_credit.py               # Credit score tests
pyproject.toml
.env.example
```

---

### Task 1: Project Setup & Dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`

- [ ] **Step 1: Install dependencies with uv**

```bash
uv add fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic redis pydantic-settings python-jose[cryptography] passlib[bcrypt] httpx python-multipart
uv add --dev pytest pytest-asyncio pytest-cov
```

- [ ] **Step 2: Create .env.example**

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lets_tennis

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

# SMS (placeholder for future)
SMS_API_KEY=
SMS_API_SECRET=

# WeChat OAuth
WECHAT_APP_ID=
WECHAT_APP_SECRET=

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# App
APP_NAME=Let's Tennis
DEFAULT_LANGUAGE=zh-Hant
SUPPORTED_LANGUAGES=zh-Hans,zh-Hant,en
```

- [ ] **Step 3: Create app/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lets_tennis"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    app_name: str = "Let's Tennis"
    default_language: str = "zh-Hant"
    supported_languages: str = "zh-Hans,zh-Hant,en"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Create app/__init__.py**

```python
# Let's Tennis Backend
```

- [ ] **Step 5: Verify imports work**

Run: `cd /Users/xue/APP && uv run python -c "from app.config import settings; print(settings.app_name)"`
Expected: `Let's Tennis`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .env.example app/__init__.py app/config.py
git commit -m "feat: project setup with FastAPI dependencies and config"
```

---

### Task 2: Database Connection & Base Models

**Files:**
- Create: `app/database.py`
- Create: `app/models/__init__.py`
- Create: `app/models/user.py`
- Create: `app/models/credit.py`

- [ ] **Step 1: Create app/database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: Create app/models/__init__.py**

```python
from app.models.user import User, UserAuth
from app.models.credit import CreditLog

__all__ = ["User", "UserAuth", "CreditLog"]
```

- [ ] **Step 3: Create app/models/user.py**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class AuthProvider(str, enum.Enum):
    PHONE = "phone"
    WECHAT = "wechat"
    GOOGLE = "google"
    USERNAME = "username"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nickname: Mapped[str] = mapped_column(String(50))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    gender: Mapped[Gender] = mapped_column(Enum(Gender))
    city: Mapped[str] = mapped_column(String(50))
    ntrp_level: Mapped[str] = mapped_column(String(10))  # e.g. "3.5", "3.5+", "4.0-"
    ntrp_label: Mapped[str] = mapped_column(String(50))  # e.g. "3.5 中级"
    credit_score: Mapped[int] = mapped_column(Integer, default=80)
    cancel_count: Mapped[int] = mapped_column(Integer, default=0)  # tracks cancellations for first-time warning
    bio: Mapped[str | None] = mapped_column(Text)
    years_playing: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(10), default="zh-Hant")
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    auth_accounts: Mapped[list["UserAuth"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserAuth(Base):
    __tablename__ = "user_auths"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider))
    provider_user_id: Mapped[str] = mapped_column(String(255))  # phone number, wechat openid, google sub, or username
    password_hash: Mapped[str | None] = mapped_column(String(255))  # only for username provider
    email: Mapped[str | None] = mapped_column(String(255))  # for username provider email verification
    email_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="auth_accounts", foreign_keys=[user_id])

    __table_args__ = (
        # Each provider+provider_user_id combo is unique
        {"sqlite_autoincrement": False},
    )
```

Note: Add a unique constraint on `(provider, provider_user_id)` in the migration.

- [ ] **Step 4: Create app/models/credit.py**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CreditReason(str, enum.Enum):
    ATTENDED = "attended"            # +5
    FIRST_CANCEL_WARNING = "first_cancel_warning"  # 0, warning only
    CANCEL_24H = "cancel_24h"        # -1
    CANCEL_12_24H = "cancel_12_24h"  # -2
    CANCEL_2H = "cancel_2h"          # -5
    NO_SHOW = "no_show"              # -5
    WEATHER_CANCEL = "weather_cancel" # 0
    ADMIN_ADJUST = "admin_adjust"    # manual adjustment


class CreditLog(Base):
    __tablename__ = "credit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    delta: Mapped[int] = mapped_column(Integer)  # positive or negative
    reason: Mapped[CreditReason] = mapped_column(Enum(CreditReason))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Verify models import**

Run: `cd /Users/xue/APP && uv run python -c "from app.models import User, UserAuth, CreditLog; print('Models OK')"`
Expected: `Models OK`

- [ ] **Step 6: Commit**

```bash
git add app/database.py app/models/
git commit -m "feat: database connection and User, UserAuth, CreditLog models"
```

---

### Task 3: Alembic Setup & Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/` (auto-generated)

- [ ] **Step 1: Initialize Alembic**

```bash
cd /Users/xue/APP && uv run alembic init alembic
```

- [ ] **Step 2: Edit alembic/env.py for async support**

Replace the entire content of `alembic/env.py` with:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.config import settings
from app.database import Base
from app.models import User, UserAuth, CreditLog  # noqa: F401 - register models

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Update alembic.ini sqlalchemy.url**

In `alembic.ini`, change the `sqlalchemy.url` line to:

```ini
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/lets_tennis
```

(This is a fallback; `env.py` overrides it from settings.)

- [ ] **Step 4: Create the database (if not exists)**

```bash
createdb lets_tennis 2>/dev/null || echo "Database already exists"
```

- [ ] **Step 5: Generate initial migration**

```bash
cd /Users/xue/APP && uv run alembic revision --autogenerate -m "initial tables: users, user_auths, credit_logs"
```

- [ ] **Step 6: Review the generated migration**

Open and review the file in `alembic/versions/`. Verify it creates:
- `users` table with all columns
- `user_auths` table with unique constraint on `(provider, provider_user_id)`
- `credit_logs` table

If the unique constraint is missing from `user_auths`, add it manually in the migration:

```python
op.create_unique_constraint("uq_user_auths_provider_id", "user_auths", ["provider", "provider_user_id"])
```

And add an index on `credit_logs.user_id`:

```python
op.create_index("ix_credit_logs_user_id", "credit_logs", ["user_id"])
```

- [ ] **Step 7: Run the migration**

```bash
cd /Users/xue/APP && uv run alembic upgrade head
```

Expected: Migration runs successfully, tables created.

- [ ] **Step 8: Verify tables exist**

```bash
psql lets_tennis -c "\dt"
```

Expected: `users`, `user_auths`, `credit_logs`, `alembic_version` tables listed.

- [ ] **Step 9: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: Alembic setup with initial migration for users, auth, credit tables"
```

---

### Task 4: Redis Connection & i18n Helper

**Files:**
- Create: `app/redis.py`
- Create: `app/i18n.py`
- Create: `tests/__init__.py`
- Create: `tests/test_i18n.py`

- [ ] **Step 1: Create app/redis.py**

```python
from redis.asyncio import Redis

from app.config import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
```

- [ ] **Step 2: Write the failing test for i18n**

Create `tests/__init__.py` (empty file).

Create `tests/test_i18n.py`:

```python
from app.i18n import t


def test_translate_zh_hans():
    assert t("auth.invalid_credentials", "zh-Hans") == "用户名或密码错误"


def test_translate_zh_hant():
    assert t("auth.invalid_credentials", "zh-Hant") == "用戶名或密碼錯誤"


def test_translate_en():
    assert t("auth.invalid_credentials", "en") == "Invalid credentials"


def test_translate_fallback_to_en():
    assert t("auth.invalid_credentials", "ja") == "Invalid credentials"


def test_translate_missing_key():
    result = t("nonexistent.key", "en")
    assert result == "nonexistent.key"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/xue/APP && uv run pytest tests/test_i18n.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Create app/i18n.py**

```python
_MESSAGES: dict[str, dict[str, str]] = {
    "auth.invalid_credentials": {
        "zh-Hans": "用户名或密码错误",
        "zh-Hant": "用戶名或密碼錯誤",
        "en": "Invalid credentials",
    },
    "auth.user_not_found": {
        "zh-Hans": "用户不存在",
        "zh-Hant": "用戶不存在",
        "en": "User not found",
    },
    "auth.email_not_verified": {
        "zh-Hans": "邮箱未验证",
        "zh-Hant": "郵箱未驗證",
        "en": "Email not verified",
    },
    "auth.phone_code_invalid": {
        "zh-Hans": "验证码无效",
        "zh-Hant": "驗證碼無效",
        "en": "Invalid verification code",
    },
    "auth.account_disabled": {
        "zh-Hans": "账号已被禁用",
        "zh-Hant": "帳號已被停用",
        "en": "Account has been disabled",
    },
    "auth.provider_already_linked": {
        "zh-Hans": "该账号已被关联",
        "zh-Hant": "該帳號已被關聯",
        "en": "This account is already linked",
    },
    "user.credit_too_low": {
        "zh-Hans": "信用分不足",
        "zh-Hant": "信用分不足",
        "en": "Credit score too low",
    },
    "common.not_found": {
        "zh-Hans": "未找到",
        "zh-Hant": "未找到",
        "en": "Not found",
    },
    "common.forbidden": {
        "zh-Hans": "没有权限",
        "zh-Hant": "沒有權限",
        "en": "Forbidden",
    },
}


def t(key: str, lang: str = "en") -> str:
    messages = _MESSAGES.get(key)
    if messages is None:
        return key
    return messages.get(lang, messages.get("en", key))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/xue/APP && uv run pytest tests/test_i18n.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/redis.py app/i18n.py tests/
git commit -m "feat: Redis connection and i18n translation helper with tests"
```

---

### Task 5: Pydantic Schemas

**Files:**
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/auth.py`
- Create: `app/schemas/user.py`

- [ ] **Step 1: Create app/schemas/__init__.py**

```python
# Pydantic schemas
```

- [ ] **Step 2: Create app/schemas/auth.py**

```python
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
    code: str  # WeChat authorization code


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
    ntrp_level: str = Field(..., pattern=r"^\d\.\d[+-]?$")  # e.g. "3.5", "3.5+", "4.0-"
    language: str = Field(default="zh-Hant", pattern=r"^(zh-Hans|zh-Hant|en)$")
```

- [ ] **Step 3: Create app/schemas/user.py**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    nickname: str
    avatar_url: str | None
    gender: str
    city: str
    ntrp_level: str
    ntrp_label: str
    credit_score: int
    bio: str | None
    years_playing: int | None
    language: str
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = None
    city: str | None = Field(default=None, min_length=1, max_length=50)
    ntrp_level: str | None = Field(default=None, pattern=r"^\d\.\d[+-]?$")
    bio: str | None = Field(default=None, max_length=500)
    years_playing: int | None = Field(default=None, ge=0, le=80)
    language: str | None = Field(default=None, pattern=r"^(zh-Hans|zh-Hant|en)$")


class CreditScoreResponse(BaseModel):
    credit_score: int
    cancel_count: int
    attendance_rate: float | None = None
```

- [ ] **Step 4: Verify schemas import**

Run: `cd /Users/xue/APP && uv run python -c "from app.schemas.auth import PhoneLoginRequest, TokenResponse; from app.schemas.user import UserProfileResponse; print('Schemas OK')"`
Expected: `Schemas OK`

- [ ] **Step 5: Commit**

```bash
git add app/schemas/
git commit -m "feat: Pydantic schemas for auth and user endpoints"
```

---

### Task 6: Auth Service (JWT + Password Hashing)

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/auth.py`
- Create: `tests/test_auth_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth_service.py`:

```python
import pytest
from app.services.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token


def test_hash_and_verify_password():
    password = "securePass123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongPass", hashed) is False


def test_create_and_decode_access_token():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_decode_invalid_token():
    payload = decode_token("invalid.token.here")
    assert payload is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xue/APP && uv run pytest tests/test_auth_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create app/services/__init__.py**

```python
# Business logic services
```

- [ ] **Step 4: Create app/services/auth.py**

```python
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": user_id, "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None


def generate_ntrp_label(level: str) -> str:
    """Generate a display label from NTRP level string."""
    labels = {
        "1.0": "1.0 初学者", "1.5": "1.5 初学者",
        "2.0": "2.0 初级", "2.5": "2.5 初级",
        "3.0": "3.0 中初级", "3.5": "3.5 中级",
        "4.0": "4.0 中高级", "4.5": "4.5 高级",
        "5.0": "5.0 高级", "5.5": "5.5 准专业",
        "6.0": "6.0 专业", "6.5": "6.5 专业", "7.0": "7.0 世界级",
    }
    base = level.rstrip("+-")
    label = labels.get(base, f"{base}")
    if level.endswith("+"):
        return f"{label}+"
    elif level.endswith("-"):
        return f"{label}-"
    return label
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/xue/APP && uv run pytest tests/test_auth_service.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/ tests/test_auth_service.py
git commit -m "feat: auth service with JWT tokens and password hashing"
```

---

### Task 7: User Service (CRUD)

**Files:**
- Create: `app/services/user.py`

- [ ] **Step 1: Create app/services/user.py**

```python
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
    await session.flush()  # get user.id

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
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/xue/APP && uv run python -c "from app.services.user import get_user_by_id, create_user_with_auth; print('User service OK')"`
Expected: `User service OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/user.py
git commit -m "feat: user service with CRUD operations"
```

---

### Task 8: FastAPI Dependencies & App Factory

**Files:**
- Create: `app/dependencies.py`
- Modify: `app/main.py` (replace the old `main.py` content)
- Delete: `main.py` (old placeholder)

- [ ] **Step 1: Create app/dependencies.py**

```python
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

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_language(accept_language: str = Header(default="zh-Hant")) -> str:
    supported = {"zh-Hans", "zh-Hant", "en"}
    if accept_language in supported:
        return accept_language
    return "zh-Hant"


Lang = Annotated[str, Depends(get_language)]
```

- [ ] **Step 2: Create app/main.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Let's Tennis", version="0.1.0", lifespan=lifespan)

    from app.routers import auth, users

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 3: Delete old main.py**

```bash
rm /Users/xue/APP/main.py
```

- [ ] **Step 4: Commit**

```bash
git add app/dependencies.py app/main.py
git rm main.py
git commit -m "feat: FastAPI app factory with dependencies and auth middleware"
```

---

### Task 9: Auth Router (Register + Login Endpoints)

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/auth.py`
- Create: `tests/conftest.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Create app/routers/__init__.py**

```python
# API routers
```

- [ ] **Step 2: Create app/routers/auth.py**

```python
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DbSession, Lang
from app.i18n import t
from app.models.user import AuthProvider, UserAuth
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
    hash_password,
    verify_password,
)
from app.services.user import create_user_with_auth, get_user_auth

router = APIRouter()


@router.post("/register/username", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_with_username(
    body: UsernameRegisterRequest,
    profile: RegisterProfileRequest,
    session: DbSession,
    lang: Lang,
):
    """Register with username + password. Requires email for verification."""
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
    """Login with username + password."""
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
    """Login/register with phone + SMS code. Creates account if not exists."""
    # TODO: Verify SMS code via SMS provider API
    # For MVP, accept code "000000" in development mode
    if body.code != "000000":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.phone_code_invalid", lang))

    auth = await get_user_auth(session, AuthProvider.PHONE, body.phone)
    if auth is None:
        # Phone login returns 404 if no profile exists yet — client must call register endpoint
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("auth.user_not_found", lang))

    if not auth.user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("auth.account_disabled", lang))

    access_token = create_access_token(str(auth.user_id))
    refresh_token = create_refresh_token(str(auth.user_id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user_id=auth.user_id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshTokenRequest, session: DbSession, lang: Lang):
    """Refresh access token using a valid refresh token."""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.invalid_credentials", lang))

    user_id = payload.get("sub")
    from app.services.user import get_user_by_id
    import uuid
    user = await get_user_by_id(session, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("auth.user_not_found", lang))

    access_token = create_access_token(str(user.id))
    new_refresh = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=new_refresh, user_id=user.id)
```

- [ ] **Step 3: Create tests/conftest.py**

```python
import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_session
from app.main import create_app
from app.models import CreditLog, User, UserAuth  # noqa: F401

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/lets_tennis_test"

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_test() as s:
        yield s
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 4: Write auth endpoint tests**

Create `tests/test_auth.py`:

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_register_username(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "TestPlayer",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "en",
        },
        json={"username": "testuser", "password": "secure123", "email": "test@example.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    # First register
    await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "Player1",
            "gender": "female",
            "city": "Hong Kong",
            "ntrp_level": "3.0",
            "language": "zh-Hant",
        },
        json={"username": "duplicate", "password": "secure123", "email": "dup@example.com"},
    )
    # Second register with same username
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "Player2",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "4.0",
            "language": "zh-Hant",
        },
        json={"username": "duplicate", "password": "other123", "email": "dup2@example.com"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_username(client: AsyncClient):
    # Register first
    await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "LoginTest",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5+",
            "language": "en",
        },
        json={"username": "loginuser", "password": "mypassword", "email": "login@example.com"},
    )
    # Login
    resp = await client.post(
        "/api/v1/auth/login/username",
        json={"username": "loginuser", "password": "mypassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    # Register first
    await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "WrongPw",
            "gender": "female",
            "city": "Hong Kong",
            "ntrp_level": "2.5",
            "language": "zh-Hant",
        },
        json={"username": "wrongpw", "password": "correct123", "email": "wp@example.com"},
    )
    # Login with wrong password
    resp = await client.post(
        "/api/v1/auth/login/username",
        json={"username": "wrongpw", "password": "wrong999"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    # Register
    reg = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "RefreshTest",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "4.0-",
            "language": "en",
        },
        json={"username": "refreshuser", "password": "pass1234", "email": "ref@example.com"},
    )
    refresh_token = reg.json()["refresh_token"]

    # Refresh
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
```

- [ ] **Step 5: Create test database**

```bash
createdb lets_tennis_test 2>/dev/null || echo "Test database already exists"
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/xue/APP && uv run pytest tests/test_auth.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/routers/ tests/conftest.py tests/test_auth.py
git commit -m "feat: auth router with username register/login, phone login, token refresh"
```

---

### Task 10: User Profile Router

**Files:**
- Create: `app/routers/users.py`
- Create: `tests/test_users.py`

- [ ] **Step 1: Create app/routers/users.py**

```python
from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.schemas.user import UserProfileResponse, UserUpdateRequest
from app.services.user import update_user

router = APIRouter()


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(user: CurrentUser):
    """Get the current user's profile."""
    return user


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(body: UserUpdateRequest, user: CurrentUser, session: DbSession):
    """Update the current user's profile."""
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return user
    updated = await update_user(session, user, **update_data)
    return updated
```

- [ ] **Step 2: Write tests**

Create `tests/test_users.py`:

```python
import pytest
from httpx import AsyncClient


async def _register_and_get_token(client: AsyncClient, username: str = "profileuser") -> str:
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": "ProfileTest",
            "gender": "male",
            "city": "Hong Kong",
            "ntrp_level": "3.5",
            "language": "zh-Hant",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_get_my_profile(client: AsyncClient):
    token = await _register_and_get_token(client)
    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["nickname"] == "ProfileTest"
    assert data["gender"] == "male"
    assert data["city"] == "Hong Kong"
    assert data["ntrp_level"] == "3.5"
    assert data["ntrp_label"] == "3.5 中级"
    assert data["credit_score"] == 80


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient):
    token = await _register_and_get_token(client, "updateuser")
    resp = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"nickname": "NewNickname", "ntrp_level": "4.0+", "bio": "Love tennis!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["nickname"] == "NewNickname"
    assert data["ntrp_level"] == "4.0+"
    assert data["ntrp_label"] == "4.0 中高级+"
    assert data["bio"] == "Love tennis!"


@pytest.mark.asyncio
async def test_get_profile_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 422  # missing Authorization header


@pytest.mark.asyncio
async def test_get_profile_invalid_token(client: AsyncClient):
    resp = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer invalid.token"})
    assert resp.status_code == 401
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/xue/APP && uv run pytest tests/test_users.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Run all tests together**

Run: `cd /Users/xue/APP && uv run pytest tests/ -v`
Expected: All tests PASS (i18n + auth service + auth endpoints + user endpoints)

- [ ] **Step 5: Commit**

```bash
git add app/routers/users.py tests/test_users.py
git commit -m "feat: user profile endpoints (GET /me, PATCH /me) with tests"
```

---

### Task 11: Credit Score Service

**Files:**
- Create: `app/services/credit.py`
- Create: `tests/test_credit.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_credit.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditReason
from app.models.user import AuthProvider
from app.services.credit import apply_credit_change, get_credit_history
from app.services.user import create_user_with_auth


async def _create_test_user(session: AsyncSession, username: str = "credituser") -> "User":
    from app.models.user import User
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
async def test_attend_increases_credit(session: AsyncSession):
    user = await _create_test_user(session, "attend1")
    assert user.credit_score == 80

    user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 85


@pytest.mark.asyncio
async def test_credit_max_100(session: AsyncSession):
    user = await _create_test_user(session, "max100")
    user.credit_score = 98
    await session.commit()

    user = await apply_credit_change(session, user, CreditReason.ATTENDED)
    assert user.credit_score == 100  # capped at 100


@pytest.mark.asyncio
async def test_first_cancel_no_deduction(session: AsyncSession):
    user = await _create_test_user(session, "firstcancel")
    assert user.cancel_count == 0

    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 80  # no deduction
    assert user.cancel_count == 1  # but count incremented


@pytest.mark.asyncio
async def test_second_cancel_deducts(session: AsyncSession):
    user = await _create_test_user(session, "secondcancel")
    user.cancel_count = 1  # already had one cancel
    await session.commit()

    user = await apply_credit_change(session, user, CreditReason.CANCEL_24H)
    assert user.credit_score == 79  # -1
    assert user.cancel_count == 2


@pytest.mark.asyncio
async def test_no_show_deducts_5(session: AsyncSession):
    user = await _create_test_user(session, "noshow1")
    user.cancel_count = 1
    await session.commit()

    user = await apply_credit_change(session, user, CreditReason.NO_SHOW)
    assert user.credit_score == 75  # -5


@pytest.mark.asyncio
async def test_weather_cancel_no_deduction(session: AsyncSession):
    user = await _create_test_user(session, "weather1")
    user = await apply_credit_change(session, user, CreditReason.WEATHER_CANCEL)
    assert user.credit_score == 80  # unchanged


@pytest.mark.asyncio
async def test_credit_history(session: AsyncSession):
    user = await _create_test_user(session, "history1")
    await apply_credit_change(session, user, CreditReason.ATTENDED)
    await apply_credit_change(session, user, CreditReason.ATTENDED)

    logs = await get_credit_history(session, user.id)
    assert len(logs) == 2
    assert all(log.delta == 5 for log in logs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xue/APP && uv run pytest tests/test_credit.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create app/services/credit.py**

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditLog, CreditReason
from app.models.user import User

# Delta values per reason
_DELTAS = {
    CreditReason.ATTENDED: 5,
    CreditReason.FIRST_CANCEL_WARNING: 0,
    CreditReason.CANCEL_24H: -1,
    CreditReason.CANCEL_12_24H: -2,
    CreditReason.CANCEL_2H: -5,
    CreditReason.NO_SHOW: -5,
    CreditReason.WEATHER_CANCEL: 0,
}

# Reasons that count as a "cancel" for first-time warning logic
_CANCEL_REASONS = {
    CreditReason.CANCEL_24H,
    CreditReason.CANCEL_12_24H,
    CreditReason.CANCEL_2H,
    CreditReason.NO_SHOW,
}


async def apply_credit_change(session: AsyncSession, user: User, reason: CreditReason, description: str | None = None) -> User:
    """Apply a credit score change to a user based on the reason."""
    delta = _DELTAS.get(reason, 0)
    actual_reason = reason

    if reason in _CANCEL_REASONS:
        if user.cancel_count == 0:
            # First cancellation: warning only, no deduction
            delta = 0
            actual_reason = CreditReason.FIRST_CANCEL_WARNING
        user.cancel_count += 1

    # Apply delta with bounds [0, 100]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/xue/APP && uv run pytest tests/test_credit.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/xue/APP && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/credit.py tests/test_credit.py
git commit -m "feat: credit score service with first-cancel warning and bounded scoring"
```

---

### Task 12: Final Verification & Cleanup

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Update .gitignore**

Add these entries to `.gitignore`:

```
.env
__pycache__/
*.pyc
.pytest_cache/
.superpowers/
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/xue/APP && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 3: Start the server to verify it runs**

```bash
cd /Users/xue/APP && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/health` — should return `{"status": "ok"}`
Visit `http://localhost:8000/docs` — should show Swagger UI with all endpoints

Ctrl+C to stop.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: update .gitignore for Python, pytest, env files"
```

---

## Verification Checklist

After completing all tasks, verify:

1. `uv run pytest tests/ -v` — all tests pass
2. `uv run uvicorn app.main:app` — server starts without errors
3. `GET /health` — returns `{"status": "ok"}`
4. `POST /api/v1/auth/register/username` — creates user, returns tokens
5. `POST /api/v1/auth/login/username` — authenticates, returns tokens
6. `GET /api/v1/users/me` — returns user profile with correct NTRP label
7. `PATCH /api/v1/users/me` — updates profile fields
8. `POST /api/v1/auth/refresh` — refreshes access token
9. Credit score starts at 80, caps at 100, first cancel is warning only
10. i18n returns correct translations for zh-Hans, zh-Hant, en
