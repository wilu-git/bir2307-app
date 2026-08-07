"""Centralized, typed application settings loaded from environment/.env.

Every other module reads configuration through this module instead of
calling os.environ directly, so there is exactly one place that knows how
settings are sourced (kept .env-based here; swapping to a different config
backend later touches only this file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_password: str
    data_dir: Path
    log_dir: Path
    uploads_dir: Path 
    generated_pdfs_dir: Path
    max_upload_mb: int = 20


def load_settings() -> Settings:
    """Build the app's Settings from environment variables, applying MVP defaults."""
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    return Settings(
        database_url=os.environ.get("DATABASE_URL", f"sqlite:///{data_dir / 'bir2307.db'}"),
        app_password=os.environ.get("APP_PASSWORD", "change-me"),
        data_dir=data_dir,
        log_dir=Path(os.environ.get("LOG_DIR", "./logs")).resolve(),
        uploads_dir=data_dir / "uploads",
        generated_pdfs_dir=data_dir / "generated_pdfs",
    )


settings = load_settings()
