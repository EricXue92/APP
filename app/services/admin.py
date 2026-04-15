import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models.admin import AdminAction, AdminAuditLog
from app.models.booking import Booking, BookingParticipant, BookingStatus, ParticipantStatus
from app.models.court import Court
from app.models.event import Event, EventParticipant, EventParticipantStatus, EventStatus
from app.models.notification import NotificationType
from app.models.report import Report, ReportStatus
from app.models.review import Review
from app.models.user import User, UserRole
from app.models.chat import Message
from app.services.notification import create_notification
from app.services.ideal_player import evaluate_ideal_status


# --- Audit Logging ---


async def log_admin_action(
    session: AsyncSession,
    *,
    admin_id: uuid.UUID,
    action: AdminAction,
    target_type: str,
    target_id: uuid.UUID,
    detail: str | None = None,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    session.add(entry)
    return entry


async def list_audit_logs(
    session: AsyncSession,
    *,
    action: str | None = None,
    admin_id: uuid.UUID | None = None,
    target_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AdminAuditLog]:
    query = select(AdminAuditLog)
    if action:
        query = query.where(AdminAuditLog.action == AdminAction(action))
    if admin_id:
        query = query.where(AdminAuditLog.admin_id == admin_id)
    if target_type:
        query = query.where(AdminAuditLog.target_type == target_type)
    query = query.order_by(AdminAuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


# --- User Management ---


async def list_users(
    session: AsyncSession,
    *,
    role: str | None = None,
    city: str | None = None,
    is_suspended: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[User]:
    query = select(User)
    if role:
        query = query.where(User.role == UserRole(role))
    if city:
        query = query.where(User.city == city)
    if is_suspended is not None:
        query = query.where(User.is_suspended == is_suspended)
    query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_user_detail(session: AsyncSession, user_id: uuid.UUID, lang: str = "en") -> dict:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(t("user.not_found", lang))

    booking_count_result = await session.execute(
        select(func.count(BookingParticipant.id))
        .join(Booking, BookingParticipant.booking_id == Booking.id)
        .where(
            BookingParticipant.user_id == user_id,
            BookingParticipant.status == ParticipantStatus.ACCEPTED,
            Booking.status == BookingStatus.COMPLETED,
        )
    )
    booking_count = booking_count_result.scalar_one()

    avg_result = await session.execute(
        select(
            func.avg(
                (Review.skill_rating + Review.punctuality_rating + Review.sportsmanship_rating)
                / 3.0
            )
        ).where(
            Review.reviewee_id == user_id,
            Review.is_hidden == False,  # noqa: E712
        )
    )
    avg_val = avg_result.scalar_one()
    avg_review = round(float(avg_val), 2) if avg_val is not None else None

    return {
        "id": user.id,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "gender": user.gender.value if hasattr(user.gender, "value") else user.gender,
        "city": user.city,
        "ntrp_level": user.ntrp_level,
        "ntrp_label": user.ntrp_label,
        "credit_score": user.credit_score,
        "cancel_count": user.cancel_count,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "is_suspended": user.is_suspended,
        "is_ideal_player": user.is_ideal_player,
        "bio": user.bio,
        "years_playing": user.years_playing,
        "language": user.language,
        "is_verified": user.is_verified,
        "is_active": user.is_active,
        "booking_count": booking_count,
        "avg_review": avg_review,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


async def suspend_user(session: AsyncSession, admin_id: uuid.UUID, user_id: uuid.UUID, lang: str = "en") -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(t("user.not_found", lang))
    if user.is_suspended:
        raise ValueError(t("admin.user_already_suspended", lang))

    user.is_suspended = True
    await log_admin_action(session, admin_id=admin_id, action=AdminAction.USER_SUSPENDED, target_type="user", target_id=user_id)
    await create_notification(session, recipient_id=user_id, type=NotificationType.ACCOUNT_SUSPENDED, target_type="user", target_id=user_id)
    await session.commit()
    await session.refresh(user)
    return user


async def unsuspend_user(session: AsyncSession, admin_id: uuid.UUID, user_id: uuid.UUID, lang: str = "en") -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(t("user.not_found", lang))
    if not user.is_suspended:
        raise ValueError(t("admin.user_not_suspended", lang))

    user.is_suspended = False
    await log_admin_action(session, admin_id=admin_id, action=AdminAction.USER_UNSUSPENDED, target_type="user", target_id=user_id)
    await session.commit()
    await session.refresh(user)
    return user


async def change_user_role(session: AsyncSession, admin_id: uuid.UUID, user_id: uuid.UUID, new_role: str, lang: str = "en") -> User:
    if admin_id == user_id:
        raise ValueError(t("admin.cannot_change_own_role", lang))

    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(t("user.not_found", lang))

    old_role = user.role.value if hasattr(user.role, "value") else user.role
    user.role = UserRole(new_role)
    await log_admin_action(
        session,
        admin_id=admin_id,
        action=AdminAction.USER_ROLE_CHANGED,
        target_type="user",
        target_id=user_id,
        detail=json.dumps({"old_role": old_role, "new_role": new_role}),
    )
    await session.commit()
    await session.refresh(user)
    return user


async def reset_user_credit(session: AsyncSession, admin_id: uuid.UUID, user_id: uuid.UUID, lang: str = "en") -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(t("user.not_found", lang))

    user.credit_score = 80
    user.cancel_count = 0
    await log_admin_action(session, admin_id=admin_id, action=AdminAction.USER_CREDIT_RESET, target_type="user", target_id=user_id)
    await evaluate_ideal_status(session, user_id)
    await session.commit()
    await session.refresh(user)
    return user


# --- Court Management ---


async def list_all_courts(
    session: AsyncSession,
    *,
    is_approved: bool | None = None,
    city: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Court]:
    query = select(Court)
    if is_approved is not None:
        query = query.where(Court.is_approved == is_approved)
    if city:
        query = query.where(Court.city == city)
    query = query.order_by(Court.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def approve_court(session: AsyncSession, admin_id: uuid.UUID, court_id: uuid.UUID, lang: str = "en") -> Court:
    court = await session.get(Court, court_id)
    if court is None:
        raise ValueError(t("court.not_found", lang))
    if court.is_approved:
        raise ValueError(t("admin.court_already_approved", lang))

    court.is_approved = True
    await log_admin_action(session, admin_id=admin_id, action=AdminAction.COURT_APPROVED, target_type="court", target_id=court_id)
    await session.commit()
    await session.refresh(court)
    return court


async def reject_court(session: AsyncSession, admin_id: uuid.UUID, court_id: uuid.UUID, lang: str = "en") -> None:
    court = await session.get(Court, court_id)
    if court is None:
        raise ValueError(t("court.not_found", lang))
    if court.is_approved:
        raise ValueError(t("admin.cannot_reject_approved_court", lang))

    await log_admin_action(session, admin_id=admin_id, action=AdminAction.COURT_REJECTED, target_type="court", target_id=court_id)
    await session.delete(court)
    await session.commit()


async def delete_court(session: AsyncSession, admin_id: uuid.UUID, court_id: uuid.UUID, lang: str = "en") -> None:
    court = await session.get(Court, court_id)
    if court is None:
        raise ValueError(t("court.not_found", lang))

    await log_admin_action(session, admin_id=admin_id, action=AdminAction.COURT_DELETED, target_type="court", target_id=court_id)
    await session.delete(court)
    await session.commit()


# --- Booking Management ---


async def list_all_bookings(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Booking]:
    query = select(Booking)
    if status:
        query = query.where(Booking.status == BookingStatus(status))
    query = query.order_by(Booking.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def admin_cancel_booking(session: AsyncSession, admin_id: uuid.UUID, booking_id: uuid.UUID, lang: str = "en") -> Booking:
    from app.services.booking import get_booking_by_id
    from app.services.chat import set_room_readonly

    booking = await get_booking_by_id(session, booking_id)
    if booking is None:
        raise ValueError(t("booking.not_found", lang))
    if booking.status == BookingStatus.CANCELLED:
        raise ValueError(t("admin.booking_already_cancelled", lang))

    booking.status = BookingStatus.CANCELLED
    await set_room_readonly(session, booking_id=booking.id)

    for p in booking.participants:
        if p.status in (ParticipantStatus.PENDING, ParticipantStatus.ACCEPTED):
            await create_notification(
                session,
                recipient_id=p.user_id,
                type=NotificationType.BOOKING_CANCELLED,
                target_type="booking",
                target_id=booking.id,
            )

    await log_admin_action(session, admin_id=admin_id, action=AdminAction.BOOKING_CANCELLED, target_type="booking", target_id=booking_id)
    await session.commit()
    await session.refresh(booking)
    return booking


# --- Event Management ---


async def list_all_events(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Event]:
    from sqlalchemy.orm import selectinload

    query = select(Event).options(selectinload(Event.participants))
    if status:
        query = query.where(Event.status == EventStatus(status))
    query = query.order_by(Event.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


async def admin_cancel_event(session: AsyncSession, admin_id: uuid.UUID, event_id: uuid.UUID, lang: str = "en") -> Event:
    from app.services.event import get_event_by_id, cancel_event

    event = await get_event_by_id(session, event_id)
    if event is None:
        raise ValueError(t("event.not_found", lang))
    if event.status == EventStatus.CANCELLED:
        raise ValueError(t("admin.event_already_cancelled", lang))

    event = await cancel_event(session, event, lang=lang)
    await log_admin_action(session, admin_id=admin_id, action=AdminAction.EVENT_CANCELLED, target_type="event", target_id=event_id)
    await session.commit()
    return event


async def admin_remove_participant(session: AsyncSession, admin_id: uuid.UUID, event_id: uuid.UUID, user_id: uuid.UUID, lang: str = "en") -> None:
    from app.services.event import get_event_by_id

    event = await get_event_by_id(session, event_id)
    if event is None:
        raise ValueError(t("event.not_found", lang))

    participant = None
    for p in event.participants:
        if p.user_id == user_id:
            participant = p
            break

    if participant is None:
        raise ValueError(t("event.not_participant", lang))

    participant.status = EventParticipantStatus.WITHDRAWN
    await log_admin_action(session, admin_id=admin_id, action=AdminAction.EVENT_PARTICIPANT_REMOVED, target_type="event", target_id=event_id, detail=json.dumps({"user_id": str(user_id)}))
    await session.commit()


# --- Chat Moderation ---


async def admin_delete_message(session: AsyncSession, admin_id: uuid.UUID, message_id: uuid.UUID, lang: str = "en") -> None:
    msg = await session.get(Message, message_id)
    if msg is None:
        raise ValueError(t("chat.room_not_found", lang))

    await log_admin_action(session, admin_id=admin_id, action=AdminAction.MESSAGE_DELETED, target_type="message", target_id=message_id)
    await session.delete(msg)
    await session.commit()


# --- Dashboard ---


async def get_dashboard_stats(session: AsyncSession) -> dict:
    total_users = (await session.execute(select(func.count(User.id)))).scalar_one()
    suspended_users = (await session.execute(select(func.count(User.id)).where(User.is_suspended == True))).scalar_one()  # noqa: E712
    pending_reports = (await session.execute(select(func.count(Report.id)).where(Report.status == ReportStatus.PENDING))).scalar_one()
    pending_courts = (await session.execute(select(func.count(Court.id)).where(Court.is_approved == False))).scalar_one()  # noqa: E712
    active_bookings = (await session.execute(select(func.count(Booking.id)).where(Booking.status.in_([BookingStatus.OPEN, BookingStatus.CONFIRMED])))).scalar_one()
    active_events = (await session.execute(select(func.count(Event.id)).where(Event.status.in_([EventStatus.OPEN, EventStatus.IN_PROGRESS])))).scalar_one()

    return {
        "total_users": total_users,
        "suspended_users": suspended_users,
        "pending_reports": pending_reports,
        "pending_courts": pending_courts,
        "active_bookings": active_bookings,
        "active_events": active_events,
    }
