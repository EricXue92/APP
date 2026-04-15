from fastapi import APIRouter

from app.routers.admin import audit, bookings, chat, courts, dashboard, events, reports, users

admin_router = APIRouter()

admin_router.include_router(users.router, prefix="/users", tags=["admin-users"])
admin_router.include_router(courts.router, prefix="/courts", tags=["admin-courts"])
admin_router.include_router(reports.router, prefix="/reports", tags=["admin-reports"])
admin_router.include_router(bookings.router, prefix="/bookings", tags=["admin-bookings"])
admin_router.include_router(events.router, prefix="/events", tags=["admin-events"])
admin_router.include_router(chat.router, prefix="/chat", tags=["admin-chat"])
admin_router.include_router(dashboard.router, prefix="/dashboard", tags=["admin-dashboard"])
admin_router.include_router(audit.router, prefix="/audit", tags=["admin-audit"])
