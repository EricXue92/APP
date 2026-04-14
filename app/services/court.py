import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court import Court, CourtType, SurfaceType


async def create_court(
    session: AsyncSession,
    *,
    name: str,
    address: str,
    city: str,
    court_type: str,
    latitude: float | None = None,
    longitude: float | None = None,
    surface_type: str | None = None,
    created_by: uuid.UUID | None = None,
    is_approved: bool = True,
) -> Court:
    court = Court(
        name=name,
        address=address,
        city=city,
        latitude=latitude,
        longitude=longitude,
        court_type=CourtType(court_type),
        surface_type=SurfaceType(surface_type) if surface_type else None,
        created_by=created_by,
        is_approved=is_approved,
    )
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def get_court_by_id(session: AsyncSession, court_id: uuid.UUID) -> Court | None:
    result = await session.execute(select(Court).where(Court.id == court_id))
    return result.scalar_one_or_none()


async def list_courts(
    session: AsyncSession,
    *,
    city: str | None = None,
    court_type: str | None = None,
    approved_only: bool = True,
) -> list[Court]:
    query = select(Court)
    if approved_only:
        query = query.where(Court.is_approved == True)
    if city:
        query = query.where(Court.city == city)
    if court_type:
        query = query.where(Court.court_type == CourtType(court_type))
    query = query.order_by(Court.name)
    result = await session.execute(query)
    return list(result.scalars().all())
