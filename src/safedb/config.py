"""Configuration: non-secret settings from config.yaml, secrets from .env.

``config.yaml`` holds the database registry and limits; ``.env`` holds secrets and runtime
switches. Both are loaded through pydantic so the rest of the code sees typed objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    """A single SQLite database the server is allowed to expose."""

    name: str
    path: str
    description: str = ""


class Limits(BaseModel):
    """Guardrails applied to every query (enforced by the safety layer in P2)."""

    max_rows_default: int = 100
    max_rows_cap: int = 1000
    timeout_s: float = 3
    max_sql_chars: int = 4000
    max_cell_chars: int = 500
    sample_rows_default: int = 3


class AppConfig(BaseModel):
    """The parsed contents of config.yaml."""

    databases: list[DatabaseConfig] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    audit_db: str = "data/audit.sqlite"

    def database(self, name: str) -> DatabaseConfig:
        """Return the registered database by name, or raise KeyError with the known names."""
        for db in self.databases:
            if db.name == name:
                return db
        known = ", ".join(d.name for d in self.databases) or "(none)"
        raise KeyError(f"unknown database {name!r}; known databases: {known}")


class Settings(BaseSettings):
    """Secrets and runtime switches, read from the environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_backend: Literal["claude_sdk", "gemini"] = "claude_sdk"
    llm_mode: Literal["live", "record", "replay"] = "replay"
    gemini_api_key: str | None = None
    daily_llm_budget: int = 200
    hints: Literal["on", "off"] = "on"
    allowed_origins: str = ""  # comma-separated CORS origins for the API (empty = allow all)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate config.yaml from ``path``."""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return AppConfig(**data)
