"""The persistent top bar: global search, a notification bell, theme
toggle, and the "+ New Import" quick action. Rendered once per view, above
that view's own content — there is no single shared layout frame Streamlit
can wrap around every view (each `with:` block is its own render pass), so
`render_top_bar()` is called at the top of every `app/ui/views/*.py`.

The search box is *global* — it feeds both the Certificates and Payees
page-local search filters at once and jumps you to whichever of those two
you aren't already on. It is deliberately distinct from each page's own
search box (e.g. Certificates' "Search by payee name or TIN…"), which only
filters that page's own list and never navigates.

The bell is a real unresolved-alert count from `event_logs` (unresolved
WARNING/ERROR entries), not a decorative badge — clicking it opens the
Audit Log pre-filtered to unresolved. There's no global quarter selector
here: Overview and Reports (the two quarter-scoped dashboards) each keep a
small page-local one via `render_quarter_picker()`, and Certificates has
its own optional Quarter/Year filter — a permanent top-bar quarter control
used to force every certificate list to hide behind whatever quarter
happens to be "current" today, which is why it isn't back.
"""

from __future__ import annotations

import streamlit as st

from app.core.logging_config import search_events
from app.core.models import EventSeverity, Payor
from app.core.payees import list_quarter_options


def _is_payor_placeholder(session) -> bool:
    payor = session.query(Payor).first()
    return payor is not None and payor.tin == "000-000-000-000"


def _unresolved_alert_count(session) -> int:
    _, warning_count = search_events(session, severity=EventSeverity.WARNING, unresolved_only=True, page_size=1)
    _, error_count = search_events(session, severity=EventSeverity.ERROR, unresolved_only=True, page_size=1)
    return warning_count + error_count


def render_top_bar(session) -> None:
    search_col, bell_col, theme_col, import_col = st.columns([5, 0.7, 0.7, 1.6], gap="small")

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
            st.session_state["certificates_filters"]["search"] = query
            st.session_state["payees_search"] = query
            if query and st.session_state["view"] not in ("certificates", "payees"):
                st.session_state["view"] = "certificates"
            st.rerun()

    with bell_col:
        unresolved = _unresolved_alert_count(session)
        if st.button(
            f"🔔 {unresolved}" if unresolved else "🔔",
            key="topbar_bell",
            help=f"{unresolved} unresolved warning/error event(s)" if unresolved else "No unresolved alerts",
            use_container_width=True,
        ):
            st.session_state["view"] = "more"
            st.session_state["more_section"] = "audit"
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


def render_quarter_picker() -> None:
    """A compact "Qn YYYY" selectbox writing to the shared `global_quarter`
    session key — used by Overview and Reports, the two pages whose whole
    dashboard is scoped to one quarter. Not shown elsewhere; Certificates'
    quarter/year filter is separate and optional (defaults to showing every
    certificate, not just one quarter's)."""
    options = list_quarter_options()
    labels = [f"Q{q} {y}" for y, q in options]
    current = st.session_state["global_quarter"]
    default_idx = options.index(current) if current in options else 0
    choice = st.selectbox(
        "Quarter",
        options=labels,
        index=default_idx,
        label_visibility="collapsed",
        key="page_quarter_picker",
    )
    chosen = options[labels.index(choice)]
    if chosen != st.session_state["global_quarter"]:
        st.session_state["global_quarter"] = chosen
        st.rerun()
