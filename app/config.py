from typing import Literal

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
    admin_email: str = (
        ""  # receives new-registration notifications; defaults to from_email if empty
    )
    search_mode: Literal["brave", "claude"] = "claude"

    model_config = {"env_file": ".env"}


settings = Settings()
