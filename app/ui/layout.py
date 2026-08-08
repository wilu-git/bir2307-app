"""The persistent page chrome: header banner + the 2-pane column split.

There is no left-nav column anymore (see app/ui/nav.py) — section
switching is `st.tabs()` at the top, so the logout control that used to
live at the bottom of the left nav now lives here, top-right of the header.
"""

from __future__ import annotations

import streamlit as st

from app.core.auth import render_logout_control


def render_app_header() -> None:
    title_col, logout_col = st.columns([5, 1])
    with title_col:
        st.title("BIR 2307 Generator")
    with logout_col:
        render_logout_control()
    st.info(
        "Payor record is currently seeded with a **placeholder TIN/address** — "
        "replace it in the database before issuing any real certificate. "
        "See README.md."
    )


def render_two_pane():
    """Returns (list_col, detail_col) column containers, ratio 2.0 : 4.0 —
    the same middle:right ratio the old 3-pane layout used, minus the
    1.1-ratio left-nav column it no longer needs. Call fresh inside each
    `with tab:` block, since `st.tabs()` renders per-tab containers rather
    than swapping a single shared layout."""
    return st.columns([2.0, 4.0], gap="small")
