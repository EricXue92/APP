# Report/Block System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add report and block functionality so users can report abusive content, block other users, and admins can resolve reports with escalating actions.

**Architecture:** Two new models (Report, Block) with their own services and routers, plus an admin router for report resolution. Block enforcement is wired into existing booking and review services. Suspension is enforced at the auth dependency level.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, pytest + httpx

---

### Task 1: Block Model + Report Model + Migration

**Files:**
- Create: `app/models/block.py`
- Create: `app/models/report.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/user.py`

- [ ] **Step 1: Create Block model**

Create `app/models/block.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_blocks_blocker_blocked"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    blocker: Mapped["User"] = relationship(foreign_keys=[blocker_id])
    blocked: Mapped["User"] = relationship(foreign_keys=[blocked_id])
```

- [ ] **Step 2: Create Report model**

Create `app/models/report.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReportTargetType(str, enum.Enum):
    USER = "user"
    REVIEW = "review"


class ReportReason(str, enum.Enum):
    NO_SHOW = "no_show"
    HARASSMENT = "harassment"
    FALSE_INFO = "false_info"
    INAPPROPRIATE = "inappropriate"
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


class ReportResolution(str, enum.Enum):
    DISMISSED = "dismissed"
    WARNED = "warned"
    CONTENT_HIDDEN = "content_hidden"
    SUSPENDED = "suspended"


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("reporter_id", "target_type", "target_id", name="uq_reports_reporter_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    reported_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[ReportTargetType] = mapped_column(Enum(ReportTargetType))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[ReportReason] = mapped_column(Enum(ReportReason))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.PENDING)
    resolution: Mapped[ReportResolution | None] = mapped_column(Enum(ReportResolution), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reporter: Mapped["User"] = relationship(foreign_keys=[reporter_id])
    reported_user: Mapped["User"] = relationship(foreign_keys=[reported_user_id])
```

- [ ] **Step 3: Add `is_suspended` to User model**

In `app/models/user.py`, add after the `is_active` field:

```python
    is_suspended: Mapped[bool] = mapped_column(default=False)
```

- [ ] **Step 4: Export new models in `__init__.py`**

Replace `app/models/__init__.py`:

```python
from app.models.user import User, UserAuth
from app.models.credit import CreditLog
from app.models.court import Court
from app.models.booking import Booking, BookingParticipant
from app.models.review import Review
from app.models.block import Block
from app.models.report import Report

__all__ = ["User", "UserAuth", "CreditLog", "Court", "Booking", "BookingParticipant", "Review", "Block", "Report"]
```

- [ ] **Step 5: Generate and apply migration**

Run:
```bash
uv run alembic revision --autogenerate -m "add blocks, reports tables and is_suspended"
uv run alembic upgrade head
```

Expected: Migration creates `blocks` table, `reports` table, and adds `is_suspended` column to `users`.

- [ ] **Step 6: Update conftest.py imports**

In `tests/conftest.py`, update the import line to include the new models so they are registered with `Base.metadata.create_all`:

```python
from app.models import Booking, BookingParticipant, Court, CreditLog, Review, User, UserAuth, Block, Report  # noqa: F401
```

- [ ] **Step 7: Commit**

```bash
git add app/models/block.py app/models/report.py app/models/user.py app/models/__init__.py alembic/versions/ tests/conftest.py
git commit -m "feat: add Block and Report models, is_suspended on User, migration"
```

---

### Task 2: i18n Keys

**Files:**
- Modify: `app/i18n.py`

- [ ] **Step 1: Add report/block i18n keys**

Add the following entries to `_MESSAGES` in `app/i18n.py`, after the existing `review.*` entries:

```python
    "block.cannot_block_self": {
        "zh-Hans": "不能拉黑自己",
        "zh-Hant": "不能封鎖自己",
        "en": "Cannot block yourself",
    },
    "block.already_blocked": {
        "zh-Hans": "已经拉黑了该用户",
        "zh-Hant": "已經封鎖了該用戶",
        "en": "User is already blocked",
    },
    "block.not_found": {
        "zh-Hans": "未找到拉黑记录",
        "zh-Hant": "未找到封鎖記錄",
        "en": "Block not found",
    },
    "report.cannot_report_self": {
        "zh-Hans": "不能举报自己",
        "zh-Hant": "不能檢舉自己",
        "en": "Cannot report yourself",
    },
    "report.already_reported": {
        "zh-Hans": "你已经举报过了",
        "zh-Hant": "你已經檢舉過了",
        "en": "You have already reported this",
    },
    "report.target_not_found": {
        "zh-Hans": "举报对象未找到",
        "zh-Hant": "檢舉對象未找到",
        "en": "Report target not found",
    },
    "report.review_already_hidden": {
        "zh-Hans": "该评价已被隐藏",
        "zh-Hant": "該評價已被隱藏",
        "en": "This review is already hidden",
    },
    "report.not_found": {
        "zh-Hans": "举报未找到",
        "zh-Hant": "檢舉未找到",
        "en": "Report not found",
    },
    "report.already_resolved": {
        "zh-Hans": "举报已处理",
        "zh-Hant": "檢舉已處理",
        "en": "Report has already been resolved",
    },
    "report.invalid_resolution_for_target": {
        "zh-Hans": "该处理方式不适用于此举报类型",
        "zh-Hant": "該處理方式不適用於此檢舉類型",
        "en": "This resolution is not valid for this report type",
    },
    "auth.account_suspended": {
        "zh-Hans": "账号已被停用",
        "zh-Hant": "帳號已被停用",
        "en": "Account has been suspended",
    },
    "common.admin_required": {
        "zh-Hans": "需要管理员权限",
        "zh-Hant": "需要管理員權限",
        "en": "Admin access required",
    },
    "block.user_blocked": {
        "zh-Hans": "操作被拒绝",
        "zh-Hant": "操作被拒絕",
        "en": "Action not allowed",
    },
```

- [ ] **Step 2: Commit**

```bash
git add app/i18n.py
git commit -m "feat: add report/block i18n keys"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `app/schemas/block.py`
- Create: `app/schemas/report.py`

- [ ] **Step 1: Create block schemas**

Create `app/schemas/block.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class BlockCreateRequest(BaseModel):
    blocked_id: uuid.UUID


class BlockResponse(BaseModel):
    id: uuid.UUID
    blocker_id: uuid.UUID
    blocked_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Create report schemas**

Create `app/schemas/report.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReportCreateRequest(BaseModel):
    reported_user_id: uuid.UUID
    target_type: str = Field(..., pattern=r"^(user|review)$")
    target_id: uuid.UUID | None = None
    reason: str = Field(..., pattern=r"^(no_show|harassment|false_info|inappropriate|other)$")
    description: str | None = Field(default=None, max_length=1000)


class ReportResponse(BaseModel):
    id: uuid.UUID
    reporter_id: uuid.UUID
    reported_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str
    description: str | None
    status: str
    resolution: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportDetailResponse(ReportResponse):
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None


class ReportResolveRequest(BaseModel):
    resolution: str = Field(..., pattern=r"^(dismissed|warned|content_hidden|suspended)$")
```

- [ ] **Step 3: Commit**

```bash
git add app/schemas/block.py app/schemas/report.py
git commit -m "feat: add block and report Pydantic schemas"
```

---

### Task 4: Block Service

**Files:**
- Create: `app/services/block.py`

- [ ] **Step 1: Write block service tests**

Create `tests/test_blocks.py`:

```python
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType


async def _register_and_get_token(client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": gender,
            "city": "Hong Kong",
            "ntrp_level": ntrp,
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_block_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "blocker1")
    token2, uid2 = await _register_and_get_token(client, "blocked1")

    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 201
    data = resp.json()
    assert data["blocker_id"] == uid1
    assert data["blocked_id"] == uid2


@pytest.mark.asyncio
async def test_block_self_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "selfblocker")

    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_block_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "dupblocker")
    token2, uid2 = await _register_and_get_token(client, "dupblocked")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    resp = await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unblock_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unblocker")
    token2, uid2 = await _register_and_get_token(client, "unblocked")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    resp = await client.delete(f"/api/v1/blocks/{uid2}", headers=_auth(token1))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_unblock_nonexistent(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "unblocker2")
    fake_id = str(uuid.uuid4())

    resp = await client.delete(f"/api/v1/blocks/{fake_id}", headers=_auth(token1))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_blocks(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "lister1")
    token2, uid2 = await _register_and_get_token(client, "listed1")
    token3, uid3 = await _register_and_get_token(client, "listed2")

    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))
    await client.post("/api/v1/blocks", json={"blocked_id": uid3}, headers=_auth(token1))

    resp = await client.get("/api/v1/blocks", headers=_auth(token1))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_blocks.py -v
```

Expected: FAIL — no router registered yet.

- [ ] **Step 3: Create block service**

Create `app/services/block.py`:

```python
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models.block import Block
from app.models.review import Review


async def create_block(
    session: AsyncSession,
    *,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
    lang: str = "en",
) -> Block:
    if blocker_id == blocked_id:
        raise ValueError(t("block.cannot_block_self", lang))

    # Check duplicate
    existing = await session.execute(
        select(Block).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError(t("block.already_blocked", lang))

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
```

- [ ] **Step 4: Commit**

```bash
git add app/services/block.py tests/test_blocks.py
git commit -m "feat: add block service with create, delete, list, and is_blocked"
```

---

### Task 5: Block Router

**Files:**
- Create: `app/routers/blocks.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create block router**

Create `app/routers/blocks.py`:

```python
import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.schemas.block import BlockCreateRequest, BlockResponse
from app.services.block import create_block, delete_block, list_blocks

router = APIRouter()


@router.post("", response_model=BlockResponse, status_code=status.HTTP_201_CREATED)
async def block_user(body: BlockCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        block = await create_block(session, blocker_id=user.id, blocked_id=body.blocked_id, lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return block


@router.delete("/{blocked_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(blocked_id: str, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        await delete_block(session, blocker_id=user.id, blocked_id=uuid.UUID(blocked_id), lang=lang)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("", response_model=list[BlockResponse])
async def get_my_blocks(user: CurrentUser, session: DbSession):
    return await list_blocks(session, user.id)
```

- [ ] **Step 2: Register block router in `app/main.py`**

Add to the imports in `create_app()`:

```python
    from app.routers import auth, blocks, bookings, courts, reviews, users
```

Add the router registration after the existing ones:

```python
    app.include_router(blocks.router, prefix="/api/v1/blocks", tags=["blocks"])
```

- [ ] **Step 3: Run block tests to verify they pass**

Run:
```bash
uv run pytest tests/test_blocks.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/routers/blocks.py app/main.py
git commit -m "feat: add block router and register in app factory"
```

---

### Task 6: Block Enforcement in Booking and Review Services

**Files:**
- Modify: `app/services/booking.py`
- Modify: `app/routers/bookings.py`
- Modify: `app/services/review.py`

- [ ] **Step 1: Write block enforcement tests**

Add to `tests/test_blocks.py`:

```python
async def _seed_court(session: AsyncSession) -> Court:
    court = Court(
        name="Test Court",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


def _future_date() -> str:
    return (date.today() + timedelta(days=7)).isoformat()


@pytest.mark.asyncio
async def test_blocked_review_submit_rejected(client: AsyncClient, session: AsyncSession):
    """New review between blocked pair should be rejected."""
    from app.models.booking import Booking
    from sqlalchemy import update as sa_update

    token1, uid1 = await _register_and_get_token(client, "blockrev1")
    token2, uid2 = await _register_and_get_token(client, "blockrev2")
    court = await _seed_court(session)

    # Create completed booking
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    await session.execute(
        sa_update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # Block user2
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Try to submit a review — should be rejected
    resp = await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
        headers=_auth(token1),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_blocked_user_cannot_join_booking(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "creator1")
    token2, uid2 = await _register_and_get_token(client, "joiner1")
    court = await _seed_court(session)

    # Creator blocks joiner
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Creator creates booking
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    # Blocked user tries to join — should fail
    resp = await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_blocked_user_bookings_hidden_from_listing(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "listcreator")
    token2, uid2 = await _register_and_get_token(client, "listviewer")
    court = await _seed_court(session)

    # Create a booking as user1
    await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )

    # User2 blocks user1
    await client.post("/api/v1/blocks", json={"blocked_id": uid1}, headers=_auth(token2))

    # User2 lists bookings — user1's booking should be hidden
    resp = await client.get("/api/v1/bookings", headers=_auth(token2))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_reviews_hidden_on_block(client: AsyncClient, session: AsyncSession):
    """When user A blocks user B, existing reviews between them should be hidden."""
    from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
    from app.models.review import Review
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "revblock1")
    token2, uid2 = await _register_and_get_token(client, "revblock2")
    court = await _seed_court(session)

    # Create completed booking
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": _future_date(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    # Backdate play_date so we can complete
    await session.execute(
        update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # Both submit reviews
    await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid2,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
        headers=_auth(token1),
    )
    await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 4,
            "punctuality_rating": 4,
            "sportsmanship_rating": 4,
        },
        headers=_auth(token2),
    )

    # Block — should hide reviews
    await client.post("/api/v1/blocks", json={"blocked_id": uid2}, headers=_auth(token1))

    # Check reviews are hidden
    from sqlalchemy import select as sa_select
    result = await session.execute(
        sa_select(Review).where(
            Review.booking_id == uuid.UUID(booking_id),
        )
    )
    reviews = list(result.scalars().all())
    assert all(r.is_hidden for r in reviews)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_blocks.py::test_blocked_user_cannot_join_booking tests/test_blocks.py::test_blocked_user_bookings_hidden_from_listing tests/test_blocks.py::test_reviews_hidden_on_block -v
```

Expected: FAIL — block check not yet in booking/review services.

- [ ] **Step 3: Add block check to booking join**

In `app/routers/bookings.py`, add import at top:

```python
from app.services.block import is_blocked
```

In the `join_existing_booking` function, after the gender check and before the capacity check, add:

```python
    # Check block relationship
    if await is_blocked(session, user.id, booking.creator_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("block.user_blocked", lang))
```

- [ ] **Step 4: Add block filter to booking list**

In `app/services/booking.py`, add imports at top:

```python
from app.models.block import Block
from sqlalchemy import and_, or_
```

Modify the `list_bookings` function signature to accept an optional `current_user_id` parameter, and add a block filter:

```python
async def list_bookings(
    session: AsyncSession,
    *,
    city: str | None = None,
    match_type: str | None = None,
    gender_requirement: str | None = None,
    current_user_id: uuid.UUID | None = None,
) -> list[Booking]:
    query = (
        select(Booking)
        .join(Booking.court)
        .where(Booking.status == BookingStatus.OPEN)
    )
    if city:
        query = query.where(Court.city == city)
    if match_type:
        query = query.where(Booking.match_type == MatchType(match_type))
    if gender_requirement:
        query = query.where(Booking.gender_requirement == GenderRequirement(gender_requirement))
    if current_user_id:
        # Exclude bookings created by users in a block relationship with current user
        blocked_ids = (
            select(Block.blocked_id)
            .where(Block.blocker_id == current_user_id)
        )
        blocker_ids = (
            select(Block.blocker_id)
            .where(Block.blocked_id == current_user_id)
        )
        query = query.where(
            Booking.creator_id.notin_(blocked_ids),
            Booking.creator_id.notin_(blocker_ids),
        )
    query = query.order_by(Booking.play_date, Booking.start_time)
    result = await session.execute(query)
    return list(result.scalars().all())
```

- [ ] **Step 5: Update bookings router to pass current_user_id**

In `app/routers/bookings.py`, modify the `get_bookings` endpoint to accept an optional authenticated user and pass it to `list_bookings`. Change the function signature:

```python
@router.get("", response_model=list[BookingResponse])
async def get_bookings(
    session: DbSession,
    user: CurrentUser,
    city: str | None = Query(default=None),
    match_type: str | None = Query(default=None, pattern=r"^(singles|doubles)$"),
    gender_requirement: str | None = Query(default=None, pattern=r"^(male_only|female_only|any)$"),
):
    bookings = await list_bookings(
        session, city=city, match_type=match_type, gender_requirement=gender_requirement,
        current_user_id=user.id,
    )
    return bookings
```

- [ ] **Step 6: Add block check to review submit**

In `app/services/review.py`, add import at top:

```python
from app.services.block import is_blocked
```

In the `submit_review` function, after the duplicate check and before creating the review, add:

```python
    # Check block relationship
    if await is_blocked(session, reviewer.id, reviewee_id):
        raise PermissionError(t("block.user_blocked", lang))
```

- [ ] **Step 7: Run all block tests**

Run:
```bash
uv run pytest tests/test_blocks.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 8: Run full test suite to check for regressions**

Run:
```bash
uv run pytest tests/ -v
```

Expected: All existing tests plus new block tests pass. Some existing booking list tests may need the `Authorization` header added if they relied on unauthenticated listing.

- [ ] **Step 9: Commit**

```bash
git add app/services/block.py app/services/booking.py app/services/review.py app/routers/bookings.py tests/test_blocks.py
git commit -m "feat: add block enforcement in booking join, listing, and review submit"
```

---

### Task 7: Suspension Enforcement

**Files:**
- Modify: `app/dependencies.py`

- [ ] **Step 1: Write suspension test**

Add to `tests/test_blocks.py`:

```python
@pytest.mark.asyncio
async def test_suspended_user_rejected(client: AsyncClient, session: AsyncSession):
    """Suspended user's token should be rejected on all protected endpoints."""
    from app.models.user import User
    from sqlalchemy import update

    token1, uid1 = await _register_and_get_token(client, "suspended1")

    # Suspend the user directly in DB
    await session.execute(
        update(User).where(User.id == uuid.UUID(uid1)).values(is_suspended=True)
    )
    await session.commit()

    # Try to access a protected endpoint
    resp = await client.get("/api/v1/blocks", headers=_auth(token1))
    assert resp.status_code == 403
    assert "suspended" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_blocks.py::test_suspended_user_rejected -v
```

Expected: FAIL — suspension check not yet in `get_current_user`.

- [ ] **Step 3: Add suspension check to `get_current_user`**

In `app/dependencies.py`, modify `get_current_user`. After the `user is None or not user.is_active` check, add:

```python
    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been suspended")
```

- [ ] **Step 4: Add admin dependency**

In `app/dependencies.py`, add at the bottom:

```python
from app.models.user import UserRole


async def require_admin(user: CurrentUser) -> User:
    if user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_blocks.py::test_suspended_user_rejected -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/dependencies.py tests/test_blocks.py
git commit -m "feat: add suspension check and admin dependency"
```

---

### Task 8: Report Service

**Files:**
- Create: `app/services/report.py`

- [ ] **Step 1: Create report service**

Create `app/services/report.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models.report import Report, ReportResolution, ReportStatus, ReportTargetType
from app.models.review import Review
from app.models.user import User


async def create_report(
    session: AsyncSession,
    *,
    reporter_id: uuid.UUID,
    reported_user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID | None,
    reason: str,
    description: str | None = None,
    lang: str = "en",
) -> Report:
    if reporter_id == reported_user_id:
        raise ValueError(t("report.cannot_report_self", lang))

    tt = ReportTargetType(target_type)

    # Determine effective target_id
    if tt == ReportTargetType.USER:
        effective_target_id = reported_user_id
    else:
        if target_id is None:
            raise ValueError(t("report.target_not_found", lang))
        effective_target_id = target_id

    # Validate review target exists and is not already hidden
    if tt == ReportTargetType.REVIEW:
        result = await session.execute(
            select(Review).where(Review.id == effective_target_id)
        )
        review = result.scalar_one_or_none()
        if review is None:
            raise ValueError(t("report.target_not_found", lang))
        if review.is_hidden:
            raise ValueError(t("report.review_already_hidden", lang))

    # Check duplicate
    existing = await session.execute(
        select(Report).where(
            Report.reporter_id == reporter_id,
            Report.target_type == tt,
            Report.target_id == effective_target_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise LookupError(t("report.already_reported", lang))

    report = Report(
        reporter_id=reporter_id,
        reported_user_id=reported_user_id,
        target_type=tt,
        target_id=effective_target_id,
        reason=reason,
        description=description,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def list_my_reports(session: AsyncSession, reporter_id: uuid.UUID) -> list[Report]:
    result = await session.execute(
        select(Report).where(Report.reporter_id == reporter_id).order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())


async def list_reports(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Report]:
    query = select(Report)
    if status:
        query = query.where(Report.status == ReportStatus(status))
    query = query.order_by(Report.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_report_by_id(session: AsyncSession, report_id: uuid.UUID) -> Report | None:
    result = await session.execute(select(Report).where(Report.id == report_id))
    return result.scalar_one_or_none()


async def resolve_report(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    resolution: str,
    admin_id: uuid.UUID,
    lang: str = "en",
) -> Report:
    report = await get_report_by_id(session, report_id)
    if report is None:
        raise ValueError(t("report.not_found", lang))

    if report.status == ReportStatus.RESOLVED:
        raise ValueError(t("report.already_resolved", lang))

    res = ReportResolution(resolution)

    # content_hidden only valid for review targets
    if res == ReportResolution.CONTENT_HIDDEN and report.target_type != ReportTargetType.REVIEW:
        raise ValueError(t("report.invalid_resolution_for_target", lang))

    # Execute side effects
    if res == ReportResolution.CONTENT_HIDDEN:
        result = await session.execute(
            select(Review).where(Review.id == report.target_id)
        )
        review = result.scalar_one_or_none()
        if review:
            review.is_hidden = True

    elif res == ReportResolution.SUSPENDED:
        result = await session.execute(
            select(User).where(User.id == report.reported_user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.is_suspended = True

    report.status = ReportStatus.RESOLVED
    report.resolution = res
    report.resolved_by = admin_id
    report.resolved_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(report)
    return report
```

- [ ] **Step 2: Commit**

```bash
git add app/services/report.py
git commit -m "feat: add report service with create, list, and resolve logic"
```

---

### Task 9: Report Router (User + Admin Endpoints)

**Files:**
- Create: `app/routers/reports.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write report tests**

Create `tests/test_reports.py`:

```python
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.court import Court, CourtType
from app.models.user import User, UserRole


async def _register_and_get_token(client: AsyncClient, username: str, gender: str = "male", ntrp: str = "3.5") -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={
            "nickname": f"Player_{username}",
            "gender": gender,
            "city": "Hong Kong",
            "ntrp_level": ntrp,
            "language": "en",
        },
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_admin(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        update(User).where(User.id == uuid.UUID(user_id)).values(role=UserRole.ADMIN)
    )
    await session.commit()


async def _seed_court(session: AsyncSession) -> Court:
    court = Court(
        name="Test Court",
        address="123 Tennis Rd",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=True,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


# --- Report User Tests ---

@pytest.mark.asyncio
async def test_report_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "reporter1")
    token2, uid2 = await _register_and_get_token(client, "reported1")

    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "user",
            "reason": "harassment",
            "description": "Rude messages",
        },
        headers=_auth(token1),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reported_user_id"] == uid2
    assert data["target_type"] == "user"
    assert data["target_id"] == uid2  # target_id = reported_user_id for user reports
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_report_hidden_review_rejected(client: AsyncClient, session: AsyncSession):
    """Cannot report a review that is already hidden."""
    from app.models.review import Review
    from sqlalchemy import update as sa_update

    token1, uid1 = await _register_and_get_token(client, "hiddenrevreporter")
    token2, uid2 = await _register_and_get_token(client, "hiddenrevreported")
    court = await _seed_court(session)

    # Create completed booking + review
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    from app.models.booking import Booking
    await session.execute(
        sa_update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    rev_resp = await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 1,
            "punctuality_rating": 1,
            "sportsmanship_rating": 1,
        },
        headers=_auth(token2),
    )
    review_id = rev_resp.json()["id"]

    # Hide the review directly
    await session.execute(
        sa_update(Review).where(Review.id == uuid.UUID(review_id)).values(is_hidden=True)
    )
    await session.commit()

    # Try to report hidden review
    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "review",
            "target_id": review_id,
            "reason": "inappropriate",
        },
        headers=_auth(token1),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_report_self_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "selfreporter")

    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid1,
            "target_type": "user",
            "reason": "other",
        },
        headers=_auth(token1),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_report_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "dupreporter")
    token2, uid2 = await _register_and_get_token(client, "dupreported")

    await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"},
        headers=_auth(token1),
    )
    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid2, "target_type": "user", "reason": "other"},
        headers=_auth(token1),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_my_reports(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "myreporter")
    token2, uid2 = await _register_and_get_token(client, "myreported")

    await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"},
        headers=_auth(token1),
    )

    resp = await client.get("/api/v1/reports/mine", headers=_auth(token1))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Report Review Tests ---

@pytest.mark.asyncio
async def test_report_review(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "revreporter1")
    token2, uid2 = await _register_and_get_token(client, "revreported1")
    court = await _seed_court(session)

    # Create completed booking and review
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    await session.execute(
        update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    # Submit a review
    rev_resp = await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 1,
            "punctuality_rating": 1,
            "sportsmanship_rating": 1,
            "comment": "Terrible",
        },
        headers=_auth(token2),
    )
    review_id = rev_resp.json()["id"]

    # Report the review (third party could report, but here uid1 reports uid2's review)
    resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "review",
            "target_id": review_id,
            "reason": "inappropriate",
        },
        headers=_auth(token1),
    )
    assert resp.status_code == 201
    assert resp.json()["target_type"] == "review"
    assert resp.json()["target_id"] == review_id


# --- Admin Tests ---

@pytest.mark.asyncio
async def test_admin_list_reports(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "adminlister")
    token2, uid2 = await _register_and_get_token(client, "adminlisted")
    await _make_admin(session, uid1)

    # Create a report as user2
    await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid1, "target_type": "user", "reason": "other"},
        headers=_auth(token2),
    )

    resp = await client.get("/api/v1/admin/reports", headers=_auth(token1))
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_non_admin_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "nonadmin")

    resp = await client.get("/api/v1/admin/reports", headers=_auth(token1))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_dismiss_report(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "admindismisser")
    token2, uid2 = await _register_and_get_token(client, "admindismissed")
    await _make_admin(session, uid1)

    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid1, "target_type": "user", "reason": "other"},
        headers=_auth(token2),
    )
    report_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "dismissed"},
        headers=_auth(token1),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert resp.json()["resolution"] == "dismissed"


@pytest.mark.asyncio
async def test_admin_hide_review(client: AsyncClient, session: AsyncSession):
    from app.models.review import Review
    from sqlalchemy import select as sa_select

    token1, uid1 = await _register_and_get_token(client, "adminhider")
    token2, uid2 = await _register_and_get_token(client, "adminhided")
    admin_token, admin_id = await _register_and_get_token(client, "hideadmin")
    await _make_admin(session, admin_id)
    court = await _seed_court(session)

    # Create completed booking + review
    resp = await client.post(
        "/api/v1/bookings",
        json={
            "court_id": str(court.id),
            "match_type": "singles",
            "play_date": (date.today() + timedelta(days=7)).isoformat(),
            "start_time": "10:00",
            "end_time": "12:00",
            "min_ntrp": "3.0",
            "max_ntrp": "4.0",
        },
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]

    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(
        f"/api/v1/bookings/{booking_id}/participants/{uid2}",
        json={"status": "accepted"},
        headers=_auth(token1),
    )
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))

    await session.execute(
        update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(
            play_date=date.today() - timedelta(days=1),
        )
    )
    await session.commit()

    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))

    rev_resp = await client.post(
        "/api/v1/reviews",
        json={
            "booking_id": booking_id,
            "reviewee_id": uid1,
            "skill_rating": 1,
            "punctuality_rating": 1,
            "sportsmanship_rating": 1,
        },
        headers=_auth(token2),
    )
    review_id = rev_resp.json()["id"]

    # Report the review
    report_resp = await client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": uid2,
            "target_type": "review",
            "target_id": review_id,
            "reason": "inappropriate",
        },
        headers=_auth(token1),
    )
    report_id = report_resp.json()["id"]

    # Admin hides content
    resp = await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "content_hidden"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["resolution"] == "content_hidden"

    # Verify review is hidden
    result = await session.execute(sa_select(Review).where(Review.id == uuid.UUID(review_id)))
    review = result.scalar_one()
    assert review.is_hidden is True


@pytest.mark.asyncio
async def test_admin_suspend_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "adminsuspender")
    token2, uid2 = await _register_and_get_token(client, "suspendee")
    await _make_admin(session, uid1)

    # Report user
    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"},
        headers=_auth(token1),
    )
    report_id = resp.json()["id"]

    # Admin suspends
    resp = await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "suspended"},
        headers=_auth(token1),
    )
    assert resp.status_code == 200

    # Verify suspended user is rejected
    resp = await client.get("/api/v1/blocks", headers=_auth(token2))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_already_resolved(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "doubleresolve1")
    token2, uid2 = await _register_and_get_token(client, "doubleresolve2")
    await _make_admin(session, uid1)

    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid1, "target_type": "user", "reason": "other"},
        headers=_auth(token2),
    )
    report_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "dismissed"},
        headers=_auth(token1),
    )

    resp = await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "warned"},
        headers=_auth(token1),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_content_hidden_invalid_for_user_report(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "invalidres1")
    token2, uid2 = await _register_and_get_token(client, "invalidres2")
    await _make_admin(session, uid1)

    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid1, "target_type": "user", "reason": "other"},
        headers=_auth(token2),
    )
    report_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "content_hidden"},
        headers=_auth(token1),
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Create report router**

Create `app/routers/reports.py`:

```python
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import AdminUser, CurrentUser, DbSession, Lang
from app.schemas.report import ReportCreateRequest, ReportDetailResponse, ReportResolveRequest, ReportResponse
from app.services.report import create_report, get_report_by_id, list_my_reports, list_reports, resolve_report

router = APIRouter()
admin_router = APIRouter()


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_report(body: ReportCreateRequest, user: CurrentUser, session: DbSession, lang: Lang):
    try:
        report = await create_report(
            session,
            reporter_id=user.id,
            reported_user_id=body.reported_user_id,
            target_type=body.target_type,
            target_id=body.target_id,
            reason=body.reason,
            description=body.description,
            lang=lang,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return report


@router.get("/mine", response_model=list[ReportResponse])
async def get_my_reports(user: CurrentUser, session: DbSession):
    return await list_my_reports(session, user.id)


# --- Admin Endpoints ---


@admin_router.get("", response_model=list[ReportDetailResponse])
async def admin_list_reports(
    admin: AdminUser,
    session: DbSession,
    report_status: str | None = Query(default=None, alias="status", pattern=r"^(pending|resolved)$"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await list_reports(session, status=report_status, limit=limit, offset=offset)


@admin_router.get("/{report_id}", response_model=ReportDetailResponse)
async def admin_get_report(report_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    report = await get_report_by_id(session, uuid.UUID(report_id))
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@admin_router.patch("/{report_id}/resolve", response_model=ReportDetailResponse)
async def admin_resolve_report(
    report_id: str,
    body: ReportResolveRequest,
    admin: AdminUser,
    session: DbSession,
    lang: Lang,
):
    try:
        report = await resolve_report(
            session,
            report_id=uuid.UUID(report_id),
            resolution=body.resolution,
            admin_id=admin.id,
            lang=lang,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return report
```

- [ ] **Step 3: Register report routers in `app/main.py`**

Update `app/main.py` to import and register both routers:

```python
    from app.routers import auth, blocks, bookings, courts, reports, reviews, users
```

Add:

```python
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
    app.include_router(reports.admin_router, prefix="/api/v1/admin/reports", tags=["admin"])
```

- [ ] **Step 4: Run all report tests**

Run:
```bash
uv run pytest tests/test_reports.py -v
```

Expected: All 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/routers/reports.py app/services/report.py app/main.py tests/test_reports.py
git commit -m "feat: add report router with user and admin endpoints"
```

---

### Task 10: Full Regression Test + CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run full test suite**

Run:
```bash
uv run pytest tests/ -v
```

Expected: All tests pass (blocks, reports, and all existing tests).

- [ ] **Step 2: Fix any regressions**

If any existing tests fail due to the `list_bookings` signature change (now requires `CurrentUser`), update those tests to pass an auth header.

- [ ] **Step 3: Update CLAUDE.md**

Add the Report/Block system to the "Key patterns" section in `CLAUDE.md`, after the review system entry:

```markdown
- **Report/Block system**: `services/report.py` + `services/block.py` + `routers/reports.py` + `routers/blocks.py` — user reports (reviews or users) with admin resolution (dismiss/warn/hide/suspend). Blocks are symmetric in effect and silent. Block enforcement: prevents booking join, hides from booking listings, hides mutual reviews, rejects new reviews between blocked pairs. `is_suspended` on User checked in `get_current_user` dependency. Admin endpoints require `AdminUser` dependency (admin or superadmin role).
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with Phase 3b report/block system"
```
