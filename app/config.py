"""Configuração centralizada da aplicação (Pydantic Settings).

Todas as variáveis de ambiente são validadas na inicialização (fail-fast).
Não acesse `os.environ` em outros lugares — use `get_settings()`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações tipadas da aplicação."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="fuel-consumption-api")
    version: str = Field(default="0.1.0")
    environment: Literal["dev", "staging", "prod"] = Field(default="dev")
    log_level: str = Field(default="INFO")

    # CORS — string CSV vinda do env é convertida em lista.
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])

    batch_size_limit: int = Field(default=100, ge=1, le=1000)
    segment_length_m: float = Field(default=100.0, gt=0.0, le=10_000.0)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"log_level inválido: {v!r}. Permitidos: {sorted(allowed)}"
            )
        return upper

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        # Aceita lista JSON do .env ou string CSV.
        if v is None or v == "":
            return ["*"]
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return v
        raise ValueError("cors_origins deve ser string CSV ou lista")

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    """Cache da configuração — avaliada uma única vez por processo."""
    return Settings()
