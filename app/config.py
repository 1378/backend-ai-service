"""Application configuration loaded from environment variables."""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_str(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _get_optional_str(key: str) -> Optional[str]:
    value = os.getenv(key)
    return value if value else None


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {key} must be an integer, got {raw!r}"
        ) from exc


class Settings:
    """Application settings sourced from environment variables and .env file."""

    APP_NAME: str
    API_PREFIX: str
    OPENAI_API_KEY: Optional[str]
    OPENAI_BASE_URL: str
    OPENAI_MODEL: str
    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    OWNER_EMAIL: Optional[str]
    RATE_LIMIT_REQUESTS: int
    RATE_LIMIT_WINDOW: int

    def __init__(self) -> None:
        self.APP_NAME = _get_str("APP_NAME", "Backend AI Service")
        self.API_PREFIX = _get_str("API_PREFIX", "/api/v1")
        self.OPENAI_API_KEY = _get_optional_str("OPENAI_API_KEY")
        self.OPENAI_BASE_URL = _get_str(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        )
        self.OPENAI_MODEL = _get_str("OPENAI_MODEL", "gpt-4o-mini")
        self.OLLAMA_BASE_URL = _get_str(
            "OLLAMA_BASE_URL",
            "http://localhost:11434/v1",
        )
        self.OLLAMA_MODEL = _get_str("OLLAMA_MODEL", "mistral")
        self.OWNER_EMAIL = _get_optional_str("OWNER_EMAIL")
        self.RATE_LIMIT_REQUESTS = _get_int("RATE_LIMIT_REQUESTS", 100)
        self.RATE_LIMIT_WINDOW = _get_int("RATE_LIMIT_WINDOW", 60)


settings = Settings()
