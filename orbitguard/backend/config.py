from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "ORBITGUARD AI Backend"
    demo_mode: bool = Field(default=True, alias="DEMO_MODE")
    overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="OVERPASS_URL",
    )
    hazard_buffer_meters: float = Field(
        default=1000,
        gt=0,
        alias="HAZARD_BUFFER_METERS",
    )
    overpass_timeout_seconds: float = Field(
        default=15,
        gt=0,
        alias="OVERPASS_TIMEOUT_SECONDS",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1/chat/completions",
        alias="OPENAI_BASE_URL",
    )
    openai_timeout_seconds: float = Field(
        default=30,
        gt=0,
        alias="OPENAI_TIMEOUT_SECONDS",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
