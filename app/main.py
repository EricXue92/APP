from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Let's Tennis", version="0.1.0", lifespan=lifespan)

    from app.routers import auth, assistant, blocks, bookings, courts, follows, matching, notifications, reports, reviews, users, weather

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(assistant.router, prefix="/api/v1/assistant", tags=["assistant"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(courts.router, prefix="/api/v1/courts", tags=["courts"])
    app.include_router(bookings.router, prefix="/api/v1/bookings", tags=["bookings"])
    app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["reviews"])
    app.include_router(blocks.router, prefix="/api/v1/blocks", tags=["blocks"])
    app.include_router(follows.router, prefix="/api/v1/follows", tags=["follows"])
    app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
    app.include_router(matching.router, prefix="/api/v1/matching", tags=["matching"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
    app.include_router(reports.admin_router, prefix="/api/v1/admin/reports", tags=["admin"])
    app.include_router(weather.router, prefix="/api/v1/weather", tags=["weather"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
