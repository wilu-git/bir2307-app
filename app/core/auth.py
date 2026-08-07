"""Login gate for the app, called once at the top of app/main.py.

`current_user` is hardcoded for the MVP's single shared-password login but
is threaded through every call site that needs it (status changes, log
resolution) so real per-user accounts can replace this function later
without touching those call sites.
"""

from __future__ import annotations

import streamlit as st

from app.config import settings

CURRENT_USER = "accounting_user"


def require_login() -> str:
    """Stop page execution here unless the session is already authenticated.

    Returns the current user's identifier for callers that need to record
    who performed an action (status_log.changed_by, event_logs.resolved_by).
    """
    if st.session_state.get("authenticated"):
        return CURRENT_USER

    st.title("BIR 2307 Generator — Sign in")
    password = st.text_input("App password", type="password")
    if st.button("Sign in"):
        if password == settings.app_password:
            st.session_state["authenticated"] = True
            st.session_state["current_user"] = CURRENT_USER
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()
    raise RuntimeError("unreachable")  # st.stop() never returns; satisfies type checkers


def render_logout_control() -> None:
    """Renders inline wherever called — the caller decides placement.

    Kept out of require_login() itself: that runs before the app's 3-pane
    layout exists, so the logout control is rendered later by app/ui/nav.py
    instead, once the left-nav column is available (staying out of
    Streamlit's default st.sidebar, per the redesign's layout goal).
    """
    st.caption(f"Signed in as {CURRENT_USER}")
    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()
