from fastapi import APIRouter

from app.dependencies import AdminUser, DbSession
from app.schemas.admin import DashboardStatsResponse
from app.services.admin import get_dashboard_stats

router = APIRouter()


@router.get("/stats", response_model=DashboardStatsResponse)
async def admin_dashboard_stats(admin: AdminUser, session: DbSession):
    stats = await get_dashboard_stats(session)
    return stats
