"""Application configuration settings."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Banking Agent backend, automation, and discovery."""

    DEMO_BANK_URL: str = "http://127.0.0.1:8000"
    HEADLESS: bool = True
    BROWSER_TIMEOUT_MS: int = 10000
    DEFAULT_VIEWPORT_WIDTH: int = 1280
    DEFAULT_VIEWPORT_HEIGHT: int = 800

    # OpenAI Settings for Discovery Mode
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    MAX_DISCOVERY_STEPS: int = 15
    DISCOVERY_TIMEOUT_SECONDS: int = 180

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
