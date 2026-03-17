from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://tradecore:tradecore@localhost:5432/tradecore"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    secret_key: str = "dev-secret-change-in-production"
    log_level: str = "INFO"
    log_json: bool = False  # Set to True in production for JSON output
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
