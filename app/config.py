from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lets_tennis"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    app_name: str = "Let's Tennis"
    default_language: str = "zh-Hant"
    supported_languages: str = "zh-Hans,zh-Hant,en"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
