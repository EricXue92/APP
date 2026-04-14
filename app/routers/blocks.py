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
