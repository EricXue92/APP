from fastapi import APIRouter

from app.dependencies import Lang
from app.schemas.ntrp_guide import LevelGuideResponse
from app.services.ntrp_guide import get_level_guide

router = APIRouter()


@router.get("/levels", response_model=LevelGuideResponse)
async def get_levels(lang: Lang):
    groups = get_level_guide(lang)
    return LevelGuideResponse(groups=groups)
