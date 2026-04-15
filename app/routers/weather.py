import uuid
from datetime import date as date_cls
from datetime import time

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.weather import WeatherResponse
from app.services.court import get_court_by_id
from app.services.weather import get_weather

router = APIRouter()


@router.get("", response_model=WeatherResponse)
async def get_weather_for_court(
    session: DbSession,
    user: CurrentUser,
    lang: Lang,
    court_id: uuid.UUID = Query(...),
    query_date: date_cls = Query(..., alias="date"),
    start_time: time | None = Query(default=None),
):
    court = await get_court_by_id(session, court_id)
    if court is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=t("court.not_found", lang))

    if court.latitude is None or court.longitude is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("weather.court_no_coordinates", lang))

    diff_days = (query_date - date_cls.today()).days
    if diff_days < 0 or diff_days > 7:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=t("weather.date_out_of_range", lang))

    result = await get_weather(
        lat=court.latitude,
        lon=court.longitude,
        query_date=query_date,
        query_time=start_time,
        court_id=court.id,
        lang=lang,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=t("weather.service_unavailable", lang))

    return result
