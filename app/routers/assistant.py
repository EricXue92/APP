from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, Lang
from app.i18n import t
from app.schemas.assistant import ParseBookingRequest, ParseBookingResponse
import app.services.assistant as _assistant_svc
from app.services.llm import RateLimitError

router = APIRouter()


@router.post("/parse-booking", response_model=ParseBookingResponse)
async def parse_booking_endpoint(
    body: ParseBookingRequest,
    user: CurrentUser,
    session: DbSession,
    lang: Lang,
):
    try:
        result = await _assistant_svc.parse_booking(session, user, body.text, lang)
    except RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=t("assistant.rate_limit", lang),
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=t("assistant.llm_error", lang),
        )

    return ParseBookingResponse(**result)
