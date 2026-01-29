"""
Pydantic Settings for Environment Variable Validation

Validates environment variables at startup and provides type-safe access.
Uses pydantic-settings for automatic .env file loading and validation.

Usage:
    from src.settings import settings

    # Access validated settings
    db_host = settings.db_host
    db_port = settings.db_port
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Database Settings
    # =========================================================================
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    db_name: str = Field(default="keiba_db", description="Database name")
    db_user: str = Field(default="postgres", description="Database user")
    db_password: str = Field(default="", description="Database password")
    db_mode: str = Field(
        default="local",
        description="Database mode: 'local' for real DB, 'mock' for testing",
    )

    # Connection pool settings
    db_pool_min_size: int = Field(default=1, ge=1, description="Minimum pool connections")
    db_pool_max_size: int = Field(default=10, ge=1, description="Maximum pool connections")

    @field_validator("db_mode")
    @classmethod
    def validate_db_mode(cls, v: str) -> str:
        allowed = {"local", "mock"}
        if v not in allowed:
            raise ValueError(f"db_mode must be one of {allowed}")
        return v

    # =========================================================================
    # Discord Bot Settings
    # =========================================================================
    discord_bot_token: str = Field(default="", description="Discord bot token")
    discord_notification_channel_id: int = Field(default=0, description="Notification channel ID")
    discord_command_channel_id: int | None = Field(default=None, description="Command channel ID")
    discord_guild_id: int | None = Field(
        default=None, description="Guild ID for faster slash command sync"
    )

    # =========================================================================
    # API Settings
    # =========================================================================
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API port")
    api_base_url: str = Field(default="http://localhost:8000", description="API base URL")

    # =========================================================================
    # LLM Settings (Gemini)
    # =========================================================================
    gemini_api_key: str = Field(default="", description="Gemini API key")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Gemini model")
    llm_provider: str = Field(default="gemini", description="LLM provider")

    # =========================================================================
    # Sentry (Error Monitoring)
    # =========================================================================
    sentry_dsn: str = Field(default="", description="Sentry DSN for error tracking")
    sentry_environment: str = Field(default="development", description="Sentry environment")
    sentry_traces_sample_rate: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Sentry traces sample rate"
    )

    # =========================================================================
    # Redis (Cache)
    # =========================================================================
    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    redis_enabled: bool = Field(default=False, description="Enable Redis caching")

    # =========================================================================
    # Logging
    # =========================================================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: 'json' or 'text'")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        allowed = {"json", "text"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"log_format must be one of {allowed}")
        return v_lower

    # =========================================================================
    # Timezone
    # =========================================================================
    tz: str = Field(default="Asia/Tokyo", description="Timezone")

    # =========================================================================
    # Helper Properties
    # =========================================================================
    @property
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode."""
        return self.db_mode == "mock"

    @property
    def has_discord_token(self) -> bool:
        """Check if Discord bot token is configured."""
        return bool(self.discord_bot_token)

    @property
    def has_sentry_dsn(self) -> bool:
        """Check if Sentry is configured."""
        return bool(self.sentry_dsn)

    @property
    def database_url(self) -> str:
        """Generate database URL for SQLAlchemy/asyncpg."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()


if __name__ == "__main__":
    # Test settings loading
    print("Settings loaded successfully:")
    print(f"  DB Host: {settings.db_host}")
    print(f"  DB Port: {settings.db_port}")
    print(f"  DB Mode: {settings.db_mode}")
    print(f"  API Port: {settings.api_port}")
    print(f"  Log Level: {settings.log_level}")
    print(f"  Mock Mode: {settings.is_mock_mode}")
