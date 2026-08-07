"""Streamlit entrypoint: password gate, DB init, navigation to pages/.

Business logic lives in app/core/ — this file and app/pages/*.py only wire
up the UI and call into core functions, per the project's separation of
concerns (keeps the door open to swap Streamlit for FastAPI+React later).
"""

from __future__ import annotations

import streamlit as st

from app.core.auth import require_login
from app.core.db import init_db
from app.core.logging_config import configure_logging

st.set_page_config(page_title="BIR 2307 Generator", page_icon="🧾", layout="wide")

configure_logging()
init_db()
require_login()

st.title("BIR 2307 Generator")
st.write(
    "Use the sidebar to upload an Excel export, generate certificates, "
    "search records, or review import/validation logs."
)
st.info(
    "Payor record is currently seeded with a **placeholder TIN/address** — "
    "replace it in the database before issuing any real certificate. "
    "See README.md."
)
