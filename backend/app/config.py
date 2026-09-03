from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://climbhub:climbhub@localhost:5432/climbhub"
    jwt_secret: str = "change-me-in-real-project"
    access_token_expire_minutes: int = 1440
    backend_cors_origins: str = "http://localhost:3000"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    backup_directory: str = ""
    backup_postgres_container: str = "climbhub-postgres"
    backup_max_upload_mb: int = 2048

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()
