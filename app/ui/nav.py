"""In-page left navigation pane — deliberately not Streamlit's built-in
multipage sidebar (see app/main.py docstring for why)."""

from __future__ import annotations

import streamlit as st

_TABS = [
    ("uploads", "📤 Uploads"),
    ("certificates", "📄 Certificates"),
    ("search", "🔍 Search"),
    ("logs", "📜 Logs"),
]


def render_left_nav() -> None:
    active = st.session_state["active_tab"]
    with st.container(key="left_nav"):
        for tab_key, label in _TABS:
            is_active = tab_key == active
            if st.button(
                label,
                key=f"nav_{tab_key}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ) and not is_active:
                st.session_state["active_tab"] = tab_key
                st.rerun()
