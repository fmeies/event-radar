from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    anthropic_api_key: str
    brave_api_key: str = ""
    database_url: str = "sqlite:////data/event_radar.db"
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str
    base_url: str = "http://localhost:8000"
    root_path: str = ""  # e.g. /event-radar when served under a URL prefix
    secure_cookies: bool = False  # set to true when serving over HTTPS
    search_mode: Literal["brave", "claude"] = "claude"
    search_sites: list[str] = []

    @field_validator("search_sites", mode="before")
    @classmethod
    def _parse_sites(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v  # type: ignore[return-value]

    model_config = {"env_file": ".env"}


settings = Settings()
