"""The persistent page chrome: header banner + the 3-pane column split."""

from __future__ import annotations

import streamlit as st


def render_app_header() -> None:
    st.title("BIR 2307 Generator")
    st.info(
        "Payor record is currently seeded with a **placeholder TIN/address** — "
        "replace it in the database before issuing any real certificate. "
        "See README.md."
    )


def render_three_pane():
    """Returns (left, middle, right) column containers, ratio 1.1 : 2.0 : 4.0."""
    return st.columns([1.1, 2.0, 4.0], gap="small")
