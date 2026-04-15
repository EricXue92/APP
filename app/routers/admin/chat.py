import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import AdminUser, DbSession, Lang
from app.services.admin import admin_delete_message

router = APIRouter()


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_chat_message(message_id: str, admin: AdminUser, session: DbSession, lang: Lang):
    try:
        await admin_delete_message(session, admin.id, uuid.UUID(message_id), lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
