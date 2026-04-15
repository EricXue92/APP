import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminAction, AdminAuditLog
from app.models.user import User, UserRole
from app.services.auth import create_access_token, generate_ntrp_label


async def _create_user(session: AsyncSession, *, role: UserRole = UserRole.USER, nickname: str = "TestUser", is_suspended: bool = False) -> User:
    user = User(
        nickname=nickname,
        gender="male",
        city="Hong Kong",
        ntrp_level="3.5",
        ntrp_label=generate_ntrp_label("3.5"),
        role=role,
        is_suspended=is_suspended,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


# --- Auth gate tests ---


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin(client: AsyncClient, session: AsyncSession):
    user = await _create_user(session)
    resp = await client.get("/api/v1/admin/users", headers=_auth_header(user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_access_superadmin_endpoints(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    target = await _create_user(session, nickname="Target", is_suspended=True)
    resp = await client.patch(f"/api/v1/admin/users/{target.id}/unsuspend", headers=_auth_header(admin))
    assert resp.status_code == 403


# --- User management tests ---


@pytest.mark.asyncio
async def test_admin_list_users(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    await _create_user(session, nickname="Player1")
    await _create_user(session, nickname="Player2")
    resp = await client.get("/api/v1/admin/users", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3  # admin + 2 players


@pytest.mark.asyncio
async def test_admin_list_users_filter_suspended(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    await _create_user(session, nickname="Active")
    await _create_user(session, nickname="Suspended", is_suspended=True)
    resp = await client.get("/api/v1/admin/users?is_suspended=true", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert all(u["is_suspended"] for u in data)


@pytest.mark.asyncio
async def test_admin_get_user_detail(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player")
    resp = await client.get(f"/api/v1/admin/users/{player.id}", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert data["nickname"] == "Player"
    assert "booking_count" in data
    assert "avg_review" in data


@pytest.mark.asyncio
async def test_admin_suspend_user(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player")
    resp = await client.patch(f"/api/v1/admin/users/{player.id}/suspend", headers=_auth_header(admin))
    assert resp.status_code == 200
    assert resp.json()["is_suspended"] is True


@pytest.mark.asyncio
async def test_superadmin_unsuspend_user(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    player = await _create_user(session, nickname="Player", is_suspended=True)
    resp = await client.patch(f"/api/v1/admin/users/{player.id}/unsuspend", headers=_auth_header(sa))
    assert resp.status_code == 200
    assert resp.json()["is_suspended"] is False


@pytest.mark.asyncio
async def test_superadmin_change_role(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    player = await _create_user(session, nickname="Player")
    resp = await client.patch(
        f"/api/v1/admin/users/{player.id}/role",
        headers=_auth_header(sa),
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_superadmin_cannot_change_own_role(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    resp = await client.patch(
        f"/api/v1/admin/users/{sa.id}/role",
        headers=_auth_header(sa),
        json={"role": "user"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_reset_credit(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player")
    player.credit_score = 50
    player.cancel_count = 3
    await session.commit()
    resp = await client.post(f"/api/v1/admin/users/{player.id}/reset-credit", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert data["credit_score"] == 80
    assert data["cancel_count"] == 0


@pytest.mark.asyncio
async def test_suspend_creates_audit_log(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player")
    await client.patch(f"/api/v1/admin/users/{player.id}/suspend", headers=_auth_header(admin))
    from sqlalchemy import select
    result = await session.execute(select(AdminAuditLog).where(AdminAuditLog.action == AdminAction.USER_SUSPENDED))
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.admin_id == admin.id
    assert log.target_id == player.id


# --- Court management tests ---


from app.models.court import Court, CourtType


async def _create_court(session: AsyncSession, *, name: str = "Test Court", is_approved: bool = False) -> Court:
    court = Court(
        name=name,
        address="123 Test St",
        city="Hong Kong",
        court_type=CourtType.OUTDOOR,
        is_approved=is_approved,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


@pytest.mark.asyncio
async def test_admin_list_courts(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    await _create_court(session, name="Pending Court", is_approved=False)
    await _create_court(session, name="Approved Court", is_approved=True)
    resp = await client.get("/api/v1/admin/courts", headers=_auth_header(admin))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_admin_list_courts_filter_pending(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    await _create_court(session, name="Pending", is_approved=False)
    await _create_court(session, name="Approved", is_approved=True)
    resp = await client.get("/api/v1/admin/courts?is_approved=false", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert all(not c["is_approved"] for c in data)


@pytest.mark.asyncio
async def test_admin_approve_court(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    court = await _create_court(session)
    resp = await client.patch(f"/api/v1/admin/courts/{court.id}/approve", headers=_auth_header(admin))
    assert resp.status_code == 200
    assert resp.json()["is_approved"] is True


@pytest.mark.asyncio
async def test_admin_reject_unapproved_court(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    court = await _create_court(session)
    resp = await client.patch(f"/api/v1/admin/courts/{court.id}/reject", headers=_auth_header(admin))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_admin_reject_approved_court_fails(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    court = await _create_court(session, is_approved=True)
    resp = await client.patch(f"/api/v1/admin/courts/{court.id}/reject", headers=_auth_header(admin))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_superadmin_delete_court(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    court = await _create_court(session, is_approved=True)
    resp = await client.delete(f"/api/v1/admin/courts/{court.id}", headers=_auth_header(sa))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_admin_cannot_delete_court(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    court = await _create_court(session, is_approved=True)
    resp = await client.delete(f"/api/v1/admin/courts/{court.id}", headers=_auth_header(admin))
    assert resp.status_code == 403


# --- Dashboard and audit tests ---


@pytest.mark.asyncio
async def test_dashboard_stats(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    resp = await client.get("/api/v1/admin/dashboard/stats", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "suspended_users" in data
    assert "pending_reports" in data
    assert "pending_courts" in data
    assert "active_bookings" in data
    assert "active_events" in data
    assert data["total_users"] >= 1  # at least the admin


@pytest.mark.asyncio
async def test_audit_log_records_actions(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player")

    # Perform an action
    await client.patch(f"/api/v1/admin/users/{player.id}/suspend", headers=_auth_header(admin))

    # Check audit log
    resp = await client.get("/api/v1/admin/audit", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["action"] == "user_suspended"
    assert data[0]["target_id"] == str(player.id)


@pytest.mark.asyncio
async def test_audit_log_filter_by_action(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player")
    court = await _create_court(session)

    await client.patch(f"/api/v1/admin/users/{player.id}/suspend", headers=_auth_header(admin))
    await client.patch(f"/api/v1/admin/courts/{court.id}/approve", headers=_auth_header(admin))

    resp = await client.get("/api/v1/admin/audit?action=user_suspended", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["action"] == "user_suspended" for e in data)


# --- Booking management tests ---


from datetime import date, time, timedelta

from app.models.booking import Booking, BookingParticipant, BookingStatus, MatchType, GenderRequirement, ParticipantStatus
from app.models.chat import ChatRoom


async def _create_approved_court(session: AsyncSession) -> "Court":
    return await _create_court(session, name="Approved Court", is_approved=True)


async def _create_open_booking(session: AsyncSession, creator: "User", court: "Court") -> Booking:
    booking = Booking(
        creator_id=creator.id,
        court_id=court.id,
        match_type=MatchType.SINGLES,
        play_date=date.today() + timedelta(days=7),
        start_time=time(10, 0),
        end_time=time(12, 0),
        min_ntrp="3.0",
        max_ntrp="4.0",
        gender_requirement=GenderRequirement.ANY,
        max_participants=2,
        status=BookingStatus.OPEN,
    )
    session.add(booking)
    await session.flush()

    participant = BookingParticipant(
        booking_id=booking.id,
        user_id=creator.id,
        status=ParticipantStatus.ACCEPTED,
    )
    session.add(participant)
    await session.commit()
    await session.refresh(booking)
    return booking


async def _create_confirmed_booking(session: AsyncSession, creator: "User", court: "Court") -> Booking:
    booking = await _create_open_booking(session, creator, court)
    booking.status = BookingStatus.CONFIRMED
    await session.commit()
    await session.refresh(booking)
    return booking


@pytest.mark.asyncio
async def test_admin_list_all_bookings(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    creator = await _create_user(session, nickname="Creator")
    court = await _create_approved_court(session)
    await _create_open_booking(session, creator, court)
    await _create_open_booking(session, creator, court)

    resp = await client.get("/api/v1/admin/bookings", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_admin_cancel_booking(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    creator = await _create_user(session, nickname="Creator")
    court = await _create_approved_court(session)
    booking = await _create_confirmed_booking(session, creator, court)

    # Create a chat room linked to this booking
    from app.services.chat import create_chat_room
    await create_chat_room(session, booking=booking, participant_ids=[creator.id], court_name="Approved Court")

    resp = await client.patch(f"/api/v1/admin/bookings/{booking.id}/cancel", headers=_auth_header(sa))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"

    # Verify chat room is readonly
    from sqlalchemy import select
    result = await session.execute(select(ChatRoom).where(ChatRoom.booking_id == booking.id))
    room = result.scalar_one_or_none()
    assert room is not None
    assert room.is_readonly is True


@pytest.mark.asyncio
async def test_admin_cancel_booking_already_cancelled(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    creator = await _create_user(session, nickname="Creator")
    court = await _create_approved_court(session)
    booking = await _create_open_booking(session, creator, court)
    booking.status = BookingStatus.CANCELLED
    await session.commit()

    resp = await client.patch(f"/api/v1/admin/bookings/{booking.id}/cancel", headers=_auth_header(sa))
    assert resp.status_code == 400


# --- Event management tests ---


from datetime import datetime, timezone

from app.models.event import Event, EventParticipant, EventParticipantStatus, EventStatus, EventType


async def _create_open_event(session: AsyncSession, creator: "User") -> Event:
    event = Event(
        creator_id=creator.id,
        name="Admin Test Cup",
        event_type=EventType.SINGLES_ELIMINATION,
        min_ntrp="3.0",
        max_ntrp="4.0",
        max_participants=8,
        registration_deadline=datetime.now(timezone.utc) + timedelta(days=7),
        status=EventStatus.OPEN,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@pytest.mark.asyncio
async def test_admin_list_all_events(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    organizer = await _create_user(session, nickname="Organizer")
    await _create_open_event(session, organizer)
    await _create_open_event(session, organizer)

    resp = await client.get("/api/v1/admin/events", headers=_auth_header(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_admin_cancel_event(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    organizer = await _create_user(session, nickname="Organizer")
    event = await _create_open_event(session, organizer)

    resp = await client.patch(f"/api/v1/admin/events/{event.id}/cancel", headers=_auth_header(sa))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_admin_cancel_event_already_cancelled(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    organizer = await _create_user(session, nickname="Organizer")
    event = await _create_open_event(session, organizer)
    event.status = EventStatus.CANCELLED
    await session.commit()

    resp = await client.patch(f"/api/v1/admin/events/{event.id}/cancel", headers=_auth_header(sa))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_remove_participant(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    organizer = await _create_user(session, nickname="Organizer")
    player = await _create_user(session, nickname="Player")
    event = await _create_open_event(session, organizer)

    # Register player in the event
    participant = EventParticipant(
        event_id=event.id,
        user_id=player.id,
        status=EventParticipantStatus.REGISTERED,
    )
    session.add(participant)
    await session.commit()

    resp = await client.delete(
        f"/api/v1/admin/events/{event.id}/participants/{player.id}",
        headers=_auth_header(sa),
    )
    assert resp.status_code == 204

    # Verify participant is WITHDRAWN
    from sqlalchemy import select
    result = await session.execute(
        select(EventParticipant).where(
            EventParticipant.event_id == event.id,
            EventParticipant.user_id == player.id,
        )
    )
    p = result.scalar_one_or_none()
    assert p is not None
    assert p.status == EventParticipantStatus.WITHDRAWN


# --- Error path tests ---


@pytest.mark.asyncio
async def test_admin_suspend_already_suspended_user(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    player = await _create_user(session, nickname="Player", is_suspended=True)

    resp = await client.patch(f"/api/v1/admin/users/{player.id}/suspend", headers=_auth_header(admin))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_unsuspend_non_suspended_user(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    player = await _create_user(session, nickname="Player")

    resp = await client.patch(f"/api/v1/admin/users/{player.id}/unsuspend", headers=_auth_header(sa))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_approve_already_approved_court(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    court = await _create_court(session, is_approved=True)

    resp = await client.patch(f"/api/v1/admin/courts/{court.id}/approve", headers=_auth_header(admin))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_get_nonexistent_user_404(client: AsyncClient, session: AsyncSession):
    admin = await _create_user(session, role=UserRole.ADMIN, nickname="Admin")
    fake_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.get(f"/api/v1/admin/users/{fake_id}", headers=_auth_header(admin))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_cancel_nonexistent_booking_400(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    fake_id = "00000000-0000-0000-0000-000000000002"

    resp = await client.patch(f"/api/v1/admin/bookings/{fake_id}/cancel", headers=_auth_header(sa))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_cancel_nonexistent_event_400(client: AsyncClient, session: AsyncSession):
    sa = await _create_user(session, role=UserRole.SUPERADMIN, nickname="SuperAdmin")
    fake_id = "00000000-0000-0000-0000-000000000003"

    resp = await client.patch(f"/api/v1/admin/events/{fake_id}/cancel", headers=_auth_header(sa))
    assert resp.status_code == 400
