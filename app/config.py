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

# Streamlit Community Cloud injects secrets.toml as st.secrets, not as OS
# env vars — mirror them in so the rest of the app (and this module) can
# keep reading plain os.environ regardless of where it's deployed. Gated on
# the file actually existing: merely importing `streamlit` and touching
# `st.secrets` with no secrets.toml present raises inside Streamlit's own
# script-run bookkeeping, which breaks `st.set_page_config()` having to be
# the first Streamlit command in main.py — so local dev/tests (no
# secrets.toml) must never reach that call at all.
_secrets_path = Path(".streamlit/secrets.toml")
if _secrets_path.exists():
    import streamlit as st

    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_password: str
    data_dir: Path
    log_dir: Path
    uploads_dir: Path
    generated_pdfs_dir: Path
    max_upload_mb: int = 20
    demo_mode: bool = False


def load_settings() -> Settings:
    """Build the app's Settings from environment variables, applying MVP defaults."""
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", f"sqlite:///{data_dir / 'bir2307.db'}"
        ),
        app_password=os.environ.get("APP_PASSWORD", "change-me"),
        data_dir=data_dir,
        log_dir=Path(os.environ.get("LOG_DIR", "./logs")).resolve(),
        uploads_dir=data_dir / "uploads",
        generated_pdfs_dir=data_dir / "generated_pdfs",
        demo_mode=os.environ.get("DEMO_MODE", "false").strip().lower()
        in {"1", "true", "yes"},
    )


settings = load_settings()
