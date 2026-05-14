import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,
    )

    app_name: str = "Context Chat API"
    app_version: str = "0.1.0"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False

    api_v_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000

    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])

    llm_provider_name: str = "Default LLM"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_default_model: str = "gpt-4o-mini"
    llm_available_models: list[str] = Field(default_factory=lambda: ["gpt-4o-mini"])

    @field_validator("debug", mode="before")
    @classmethod
    def parse_bool(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    @field_validator("cors_origins", "trusted_hosts", "llm_available_models", mode="before")
    @classmethod
    def parse_env_list(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.startswith("[") and normalized.endswith("]"):
                try:
                    decoded = json.loads(normalized)
                    if isinstance(decoded, list):
                        return [str(item).strip() for item in decoded if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in normalized.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def include_default_llm_model(self) -> "Settings":
        if self.llm_default_model and self.llm_default_model not in self.llm_available_models:
            self.llm_available_models.insert(0, self.llm_default_model)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
