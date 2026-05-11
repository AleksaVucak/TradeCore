from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://tradecore:tradecore@localhost:5432/tradecore"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    secret_key: str = "dev-secret-change-in-production"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Email / SMTP — when MAIL_ENABLED=false the verification link is logged to stdout
    mail_enabled: bool = False
    mail_smtp_host: str = "smtp.gmail.com"
    mail_smtp_port: int = 587
    mail_smtp_user: str = ""
    mail_smtp_password: str = ""
    mail_from_address: str = "noreply@tradecore.dev"
    mail_from_name: str = "TradeCore"

    # Frontend URL used for building verification links
    frontend_url: str = "http://localhost:3000"

    # NewsAPI key for sentiment pipeline (Phase 17.1)
    newsapi_key: str = ""

    # Verification-token lifetime in minutes
    verification_token_expire_minutes: int = 60

    # Minimum seconds between verification-email resends
    verification_resend_cooldown_seconds: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
