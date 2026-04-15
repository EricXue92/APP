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
    resp = await client.post(
        "/api/v1/auth/register/username",
        params={"nickname": f"Player_{username}", "gender": gender, "city": "Hong Kong", "ntrp_level": ntrp, "language": "en"},
        json={"username": username, "password": "pass1234", "email": f"{username}@example.com"},
    )
    data = resp.json()
    return data["access_token"], data["user_id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_admin(session: AsyncSession, user_id: str) -> None:
    await session.execute(update(User).where(User.id == uuid.UUID(user_id)).values(role=UserRole.ADMIN))
    await session.commit()


async def _seed_court(session: AsyncSession) -> Court:
    court = Court(name="Test Court", address="123 Tennis Rd", city="Hong Kong", court_type=CourtType.OUTDOOR, is_approved=True)
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _create_completed_booking_and_review(client, session, token1, uid1, token2, uid2, court):
    """Helper: create completed booking, submit review from token2 about uid1. Returns (booking_id, review_id)."""
    resp = await client.post(
        "/api/v1/bookings",
        json={"court_id": str(court.id), "match_type": "singles", "play_date": (date.today() + timedelta(days=7)).isoformat(), "start_time": "10:00", "end_time": "12:00", "min_ntrp": "3.0", "max_ntrp": "4.0"},
        headers=_auth(token1),
    )
    booking_id = resp.json()["id"]
    await client.post(f"/api/v1/bookings/{booking_id}/join", headers=_auth(token2))
    await client.patch(f"/api/v1/bookings/{booking_id}/participants/{uid2}", json={"status": "accepted"}, headers=_auth(token1))
    await client.post(f"/api/v1/bookings/{booking_id}/confirm", headers=_auth(token1))
    await session.execute(update(Booking).where(Booking.id == uuid.UUID(booking_id)).values(play_date=date.today() - timedelta(days=1)))
    await session.commit()
    await client.post(f"/api/v1/bookings/{booking_id}/complete", headers=_auth(token1))
    rev_resp = await client.post(
        "/api/v1/reviews",
        json={"booking_id": booking_id, "reviewee_id": uid1, "skill_rating": 1, "punctuality_rating": 1, "sportsmanship_rating": 1, "comment": "Terrible"},
        headers=_auth(token2),
    )
    review_id = rev_resp.json()["id"]
    return booking_id, review_id


# --- Report User Tests ---

@pytest.mark.asyncio
async def test_report_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "reporter1")
    token2, uid2 = await _register_and_get_token(client, "reported1")
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment", "description": "Rude messages"}, headers=_auth(token1))
    assert resp.status_code == 201
    data = resp.json()
    assert data["reported_user_id"] == uid2
    assert data["target_type"] == "user"
    assert data["target_id"] == uid2
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_report_hidden_review_rejected(client: AsyncClient, session: AsyncSession):
    from app.models.review import Review
    from sqlalchemy import update as sa_update
    token1, uid1 = await _register_and_get_token(client, "hiddenrevreporter")
    token2, uid2 = await _register_and_get_token(client, "hiddenrevreported")
    court = await _seed_court(session)
    _, review_id = await _create_completed_booking_and_review(client, session, token1, uid1, token2, uid2, court)
    await session.execute(sa_update(Review).where(Review.id == uuid.UUID(review_id)).values(is_hidden=True))
    await session.commit()
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "review", "target_id": review_id, "reason": "inappropriate"}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_report_self_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "selfreporter")
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid1, "target_type": "user", "reason": "other"}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_report_rejected(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "dupreporter")
    token2, uid2 = await _register_and_get_token(client, "dupreported")
    await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"}, headers=_auth(token1))
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "user", "reason": "other"}, headers=_auth(token1))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_my_reports(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "myreporter")
    token2, uid2 = await _register_and_get_token(client, "myreported")
    await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"}, headers=_auth(token1))
    resp = await client.get("/api/v1/reports/mine", headers=_auth(token1))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Report Review Tests ---

@pytest.mark.asyncio
async def test_report_review(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "revreporter1")
    token2, uid2 = await _register_and_get_token(client, "revreported1")
    court = await _seed_court(session)
    _, review_id = await _create_completed_booking_and_review(client, session, token1, uid1, token2, uid2, court)
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "review", "target_id": review_id, "reason": "inappropriate"}, headers=_auth(token1))
    assert resp.status_code == 201
    assert resp.json()["target_type"] == "review"
    assert resp.json()["target_id"] == review_id


# --- Admin Tests ---

@pytest.mark.asyncio
async def test_admin_list_reports(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "adminlister")
    token2, uid2 = await _register_and_get_token(client, "adminlisted")
    await _make_admin(session, uid1)
    await client.post("/api/v1/reports", json={"reported_user_id": uid1, "target_type": "user", "reason": "other"}, headers=_auth(token2))
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
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid1, "target_type": "user", "reason": "other"}, headers=_auth(token2))
    report_id = resp.json()["id"]
    resp = await client.patch(f"/api/v1/admin/reports/{report_id}/resolve", json={"resolution": "dismissed"}, headers=_auth(token1))
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
    _, review_id = await _create_completed_booking_and_review(client, session, token1, uid1, token2, uid2, court)
    report_resp = await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "review", "target_id": review_id, "reason": "inappropriate"}, headers=_auth(token1))
    report_id = report_resp.json()["id"]
    resp = await client.patch(f"/api/v1/admin/reports/{report_id}/resolve", json={"resolution": "content_hidden"}, headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["resolution"] == "content_hidden"
    result = await session.execute(sa_select(Review).where(Review.id == uuid.UUID(review_id)))
    review = result.scalar_one()
    assert review.is_hidden is True


@pytest.mark.asyncio
async def test_admin_suspend_user(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "adminsuspender")
    token2, uid2 = await _register_and_get_token(client, "suspendee")
    await _make_admin(session, uid1)
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"}, headers=_auth(token1))
    report_id = resp.json()["id"]
    resp = await client.patch(f"/api/v1/admin/reports/{report_id}/resolve", json={"resolution": "suspended"}, headers=_auth(token1))
    assert resp.status_code == 200
    resp = await client.get("/api/v1/blocks", headers=_auth(token2))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_already_resolved(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "doubleresolve1")
    token2, uid2 = await _register_and_get_token(client, "doubleresolve2")
    await _make_admin(session, uid1)
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid1, "target_type": "user", "reason": "other"}, headers=_auth(token2))
    report_id = resp.json()["id"]
    await client.patch(f"/api/v1/admin/reports/{report_id}/resolve", json={"resolution": "dismissed"}, headers=_auth(token1))
    resp = await client.patch(f"/api/v1/admin/reports/{report_id}/resolve", json={"resolution": "warned"}, headers=_auth(token1))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_content_hidden_invalid_for_user_report(client: AsyncClient, session: AsyncSession):
    token1, uid1 = await _register_and_get_token(client, "invalidres1")
    token2, uid2 = await _register_and_get_token(client, "invalidres2")
    await _make_admin(session, uid1)
    resp = await client.post("/api/v1/reports", json={"reported_user_id": uid1, "target_type": "user", "reason": "other"}, headers=_auth(token2))
    report_id = resp.json()["id"]
    resp = await client.patch(f"/api/v1/admin/reports/{report_id}/resolve", json={"resolution": "content_hidden"}, headers=_auth(token1))
    assert resp.status_code == 400


# --- Gap Tests ---

@pytest.mark.asyncio
async def test_warned_resolution_creates_notification(client: AsyncClient, session: AsyncSession):
    """Resolving a report with 'warned' sends an ACCOUNT_WARNED notification to the reported user."""
    from sqlalchemy import select as sa_select
    from app.models.notification import Notification, NotificationType

    reporter_token, reporter_id = await _register_and_get_token(client, "warnreporter")
    reported_token, reported_id = await _register_and_get_token(client, "warnreported")
    admin_token, admin_id = await _register_and_get_token(client, "warnadmin")
    await _make_admin(session, admin_id)

    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": reported_id, "target_type": "user", "reason": "harassment"},
        headers=_auth(reporter_token),
    )
    assert resp.status_code == 201
    report_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"resolution": "warned"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert resp.json()["resolution"] == "warned"

    # Verify ACCOUNT_WARNED notification was created for the reported user
    result = await session.execute(
        sa_select(Notification).where(
            Notification.recipient_id == uuid.UUID(reported_id),
            Notification.type == NotificationType.ACCOUNT_WARNED,
        )
    )
    notification = result.scalar_one_or_none()
    assert notification is not None


@pytest.mark.asyncio
async def test_list_reports_with_status_filter(client: AsyncClient, session: AsyncSession):
    """Admin can filter reports by status=pending and status=resolved."""
    token1, uid1 = await _register_and_get_token(client, "filterreporter1")
    token2, uid2 = await _register_and_get_token(client, "filterreported1")
    token3, uid3 = await _register_and_get_token(client, "filterreported2")
    admin_token, admin_id = await _register_and_get_token(client, "filteradmin")
    await _make_admin(session, admin_id)

    # Create two reports
    resp1 = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid2, "target_type": "user", "reason": "harassment"},
        headers=_auth(token1),
    )
    report1_id = resp1.json()["id"]

    resp2 = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid3, "target_type": "user", "reason": "other"},
        headers=_auth(token1),
    )
    report2_id = resp2.json()["id"]

    # Resolve one of them
    await client.patch(
        f"/api/v1/admin/reports/{report1_id}/resolve",
        json={"resolution": "dismissed"},
        headers=_auth(admin_token),
    )

    # Filter by pending — should include report2, not report1
    resp = await client.get("/api/v1/admin/reports?status=pending", headers=_auth(admin_token))
    assert resp.status_code == 200
    pending_ids = [r["id"] for r in resp.json()]
    assert report2_id in pending_ids
    assert report1_id not in pending_ids

    # Filter by resolved — should include report1, not report2
    resp = await client.get("/api/v1/admin/reports?status=resolved", headers=_auth(admin_token))
    assert resp.status_code == 200
    resolved_ids = [r["id"] for r in resp.json()]
    assert report1_id in resolved_ids
    assert report2_id not in resolved_ids


@pytest.mark.asyncio
async def test_empty_reports_list(client: AsyncClient, session: AsyncSession):
    """A user who has never filed a report sees an empty list."""
    token, uid = await _register_and_get_token(client, "noreportuser")
    resp = await client.get("/api/v1/reports/mine", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_report_nonexistent_review_target(client: AsyncClient, session: AsyncSession):
    """Reporting a review with a random UUID that doesn't exist should return 400."""
    token1, uid1 = await _register_and_get_token(client, "badrevreporter")
    token2, uid2 = await _register_and_get_token(client, "badrevreported")
    fake_review_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/reports",
        json={"reported_user_id": uid2, "target_type": "review", "target_id": fake_review_id, "reason": "inappropriate"},
        headers=_auth(token1),
    )
    assert resp.status_code == 400
