from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Ozon Ads API")
    app_env: str = os.getenv("APP_ENV", "development")
    debug: bool = os.getenv("APP_DEBUG", "1").strip().lower() in {"1", "true", "yes"}
    api_prefix: str = os.getenv("API_PREFIX", "/api")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    timezone: str = os.getenv("TZ", "Europe/Moscow")


def get_settings() -> Settings:
    return Settings()
