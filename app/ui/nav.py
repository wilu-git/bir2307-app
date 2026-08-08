"""Top navigation — Streamlit's native `st.tabs()`, replacing the old
custom-styled left-nav column (there is no sidebar in this app)."""

from __future__ import annotations

import streamlit as st

_TAB_LABELS = ["📇 Payees", "📤 Uploads", "📜 Logs"]


def render_top_tabs():
    """Returns (payees_tab, uploads_tab, logs_tab) container contexts."""
    return st.tabs(_TAB_LABELS)
