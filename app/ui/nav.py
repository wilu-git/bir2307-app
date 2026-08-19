"""Persistent left sidebar: logo, primary navigation, account footer.

Native `st.sidebar` — always dark regardless of the app's light/dark
toggle (see styles.py), matching the source design's fixed sidebar color.
Section-switching is plain session_state + st.rerun(), same pattern the
old st.tabs()-based nav used, just one level up (5 destinations instead of
3 tabs, plus a "More" destination with its own internal sub-nav).
"""

from __future__ import annotations

import streamlit as st

from app.core.auth import CURRENT_USER

_NAV_ITEMS = [
    ("overview", "Overview"),
    ("certificates", "Certificates"),
    ("payees", "Payees"),
    ("reports", "Reports"),
    ("more", "More"),
]


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;padding:6px 0 18px 0;">
              <div style="width:32px;height:32px;border-radius:6px;background:#2563EB;
                          display:flex;align-items:center;justify-content:center;
                          flex-shrink:0;">
                <span style="color:#fff;font-family:'Plus Jakarta Sans',sans-serif;
                             font-weight:800;font-size:11px;">2307</span>
              </div>
              <div style="line-height:1.25;">
                <div style="color:#E2E8F0;font-size:13px;font-weight:600;">BIR 2307</div>
                <div style="color:#64748B;font-size:11px;">Generator</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for view_key, label in _NAV_ITEMS:
            active = st.session_state["view"] == view_key
            if st.button(
                label,
                key=f"nav_{view_key}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state["view"] = view_key
                st.rerun()

        st.divider()
        st.caption(f"Signed in as {CURRENT_USER}")
        if st.button("Log out", use_container_width=True, key="nav_logout"):
            st.session_state.clear()
            st.rerun()
