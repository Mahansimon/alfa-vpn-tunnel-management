"""تنظیمات مرکزی برنامه. همه مقادیر از فایل .env خوانده می‌شوند."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"
API_PREFIX = "/api/v1"
MIN_AGENT_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- عمومی ---
    ENVIRONMENT: Literal["development", "testing", "production"] = "production"
    DEBUG: bool = False
    PANEL_NAME: str = "Alfa VpnTunnel Managment"
    PANEL_URL: str = "http://localhost"
    PANEL_PORT: int = 8080
    TIMEZONE: str = "Asia/Tehran"
    LOG_LEVEL: str = "INFO"
    ENABLE_DOCS: bool = False

    # --- دیتابیس ---
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "alfa"
    POSTGRES_USER: str = "alfa"
    POSTGRES_PASSWORD: str = "change-me"
    DATABASE_URL: str | None = None

    # --- Redis ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str | None = None
    REDIS_ENABLED: bool = True

    # --- امنیت ---
    SECRET_KEY: str = Field(default="insecure-dev-secret-change-me", min_length=16)
    SECRETS_ENCRYPTION_KEY: str = ""
    SESSION_TTL_MINUTES: int = 720
    JWT_ALGORITHM: str = "HS256"
    COOKIE_NAME: str = "alfa_session"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    CSRF_COOKIE_NAME: str = "alfa_csrf"
    CORS_ORIGINS: str = ""
    PASSWORD_MIN_LENGTH: int = 12
    LOGIN_RATE_LIMIT: str = "10/5m"
    API_RATE_LIMIT: str = "300/1m"
    AGENT_RATE_LIMIT: str = "600/1m"
    MAX_FAILED_LOGINS: int = 8
    LOCKOUT_MINUTES: int = 15
    ENABLE_2FA: bool = True

    # --- Agent ---
    AGENT_PORT: int = 9443
    AGENT_TLS_VERIFY: bool = False
    AGENT_REQUEST_TIMEOUT: int = 20
    AGENT_HEARTBEAT_INTERVAL: int = 15
    AGENT_OFFLINE_AFTER_MISSED: int = 3
    AGENT_TOKEN_ROTATION_DAYS: int = 30

    # --- مانیتورینگ / نگهداشت داده ---
    METRICS_INTERVAL_SECONDS: int = 20
    METRIC_RETENTION_DAYS: int = 7
    METRIC_AGG_RETENTION_DAYS: int = 180
    TRAFFIC_RETENTION_DAYS: int = 365
    LOG_RETENTION_DAYS: int = 30
    SCHEDULER_ENABLED: bool = True

    # --- حالت توسعه ---
    MOCK_MODE: bool = False
    DEMO_DATA: bool = False

    # --- مسیرها ---
    DATA_DIR: str = "/var/lib/alfa"
    BACKUP_DIR: str = "/var/lib/alfa/backups"
    TUNNEL_BINARY_DIR: str = "/opt/alfa/tunnel-binaries"

    # --- منابع تونل‌ها (بعداً توسط کاربر پر می‌شود) ---
    PREMIUM_BACKHAUL_BINARY: str = ""
    BROKEN_NODE_BINARY: str = ""
    PACKET_TUNNEL_REPOSITORY: str = ""
    PACKET_TUNNEL_REF: str = ""
    BACKPACK_REPOSITORY: str = ""
    BACKPACK_REF: str = ""
    PING_TUNNEL_REPOSITORY: str = ""
    PING_TUNNEL_REF: str = ""
    RATHOLE_REPOSITORY: str = ""
    RATHOLE_REF: str = ""
    GITHUB_TOKEN: str = ""

    @field_validator("MOCK_MODE")
    @classmethod
    def _no_mock_in_production(cls, v: bool, info) -> bool:
        # قانون: در Production هرگز داده جعلی نمایش داده نمی‌شود
        if v and info.data.get("ENVIRONMENT") == "production":
            return False
        return v

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def redis_url(self) -> str:
        return self.REDIS_URL or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
