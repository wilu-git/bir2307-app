"""The persistent top bar: global search, quarter selector, theme toggle,
and the "+ New Import" quick action. Rendered once per view, above that
view's own content — there is no single shared layout frame Streamlit can
wrap around every view (each `with:` block is its own render pass), so
`render_top_bar()` is called at the top of every `app/ui/views/*.py`.
"""

from __future__ import annotations

import streamlit as st

from app.core.models import Payor
from app.core.payees import list_quarter_options


def _is_payor_placeholder(session) -> bool:
    payor = session.query(Payor).first()
    return payor is not None and payor.tin == "000-000-000-000"


def render_top_bar(session) -> None:
    search_col, quarter_col, theme_col, import_col = st.columns([3, 1.3, 0.7, 1.3], gap="small")

    with search_col:
        query = st.text_input(
            "Search",
            value=st.session_state["global_search"],
            placeholder="Search payees, TIN, certificate…",
            label_visibility="collapsed",
            key="topbar_search",
        )
        if query != st.session_state["global_search"]:
            st.session_state["global_search"] = query
            if query:
                st.session_state["view"] = "certificates"
                st.session_state["certificates_filters"]["search"] = query
                st.rerun()

    with quarter_col:
        options = list_quarter_options()
        labels = [f"Q{q} {y}" for y, q in options]
        current = st.session_state["global_quarter"]
        default_idx = options.index(current) if current in options else 0
        choice = st.selectbox(
            "Quarter", options=labels, index=default_idx, label_visibility="collapsed", key="topbar_quarter"
        )
        chosen = options[labels.index(choice)]
        if chosen != st.session_state["global_quarter"]:
            st.session_state["global_quarter"] = chosen
            st.rerun()

    with theme_col:
        is_dark = st.session_state["theme"] == "dark"
        if st.button("🌙" if not is_dark else "☀️", key="topbar_theme", help="Toggle light/dark theme"):
            st.session_state["theme"] = "light" if is_dark else "dark"
            st.rerun()

    with import_col:
        if st.button("+ New Import", type="primary", use_container_width=True, key="topbar_new_import"):
            st.session_state["import_wizard_open"] = True
            st.session_state["import_wizard_stage"] = "upload"
            st.rerun()

    if _is_payor_placeholder(session):
        st.info(
            "Payor record is currently seeded with a **placeholder TIN/address** — "
            "replace it in **More → Settings** before issuing any real certificate."
        )

    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)
