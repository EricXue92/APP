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

    # LLM / Booking Assistant
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    assistant_rate_limit: int = 10  # per user per hour

    # QWeather (天气)
    qweather_api_key: str = ""
    qweather_base_url: str = "https://devapi.qweather.com"

    # Push notifications (FCM)
    firebase_credentials_path: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
