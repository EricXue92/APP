from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Let's Tennis", version="0.1.0", lifespan=lifespan)

    from app.routers import auth, assistant, blocks, bookings, chat, courts, events, follows, matching, notifications, reports, reviews, users, weather
    from app.routers.admin import admin_router

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(assistant.router, prefix="/api/v1/assistant", tags=["assistant"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(courts.router, prefix="/api/v1/courts", tags=["courts"])
    app.include_router(bookings.router, prefix="/api/v1/bookings", tags=["bookings"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["reviews"])
    app.include_router(blocks.router, prefix="/api/v1/blocks", tags=["blocks"])
    app.include_router(follows.router, prefix="/api/v1/follows", tags=["follows"])
    app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
    app.include_router(matching.router, prefix="/api/v1/matching", tags=["matching"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
    app.include_router(weather.router, prefix="/api/v1/weather", tags=["weather"])
    app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
