from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Let's Tennis", version="0.1.0", lifespan=lifespan)

    from app.routers import auth, courts, users

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(courts.router, prefix="/api/v1/courts", tags=["courts"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
