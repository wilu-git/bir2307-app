"""Logs page: filterable event_logs viewer with a one-time resolve action.

Read-only for the historical fields (category, severity, message,
technical_detail, created_at) — the only write this page performs is
filling in the resolved_* columns via `resolve_event`, which is itself a
no-op past the first resolution. No update/delete path exists here for
anything else in this table.
"""

from __future__ import annotations

import streamlit as st

from app.core.auth import require_login
from app.core.db import SessionLocal, init_db
from app.core.logging_config import configure_logging, resolve_event, search_events
from app.core.models import EventCategory, EventSeverity

configure_logging()
init_db()
current_user = require_login()

st.title("Logs")

PAGE_SIZE = 25

col1, col2, col3 = st.columns(3)
with col1:
    category_query = st.selectbox("Category", options=["(all)"] + [c.value for c in EventCategory])
with col2:
    severity_query = st.selectbox("Severity", options=["(all)"] + [s.value for s in EventSeverity])
with col3:
    unresolved_only = st.checkbox("Unresolved only", value=True)

if "logs_page" not in st.session_state:
    st.session_state["logs_page"] = 1

filters_key = (category_query, severity_query, unresolved_only)
if st.session_state.get("logs_last_filters_key") != filters_key:
    st.session_state["logs_page"] = 1
    st.session_state["logs_last_filters_key"] = filters_key

category_filter = EventCategory(category_query) if category_query != "(all)" else None
severity_filter = EventSeverity(severity_query) if severity_query != "(all)" else None

with SessionLocal() as session:
    events, total_count = search_events(
        session,
        category=category_filter,
        severity=severity_filter,
        unresolved_only=unresolved_only,
        page=st.session_state["logs_page"],
        page_size=PAGE_SIZE,
    )
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    st.caption(
        f"{total_count} matching log entr{'y' if total_count == 1 else 'ies'} — page {st.session_state['logs_page']} of {total_pages}"
    )

    if not events:
        st.info("No log entries match these filters.")

    icon = {EventSeverity.ERROR: "🔴", EventSeverity.WARNING: "🟡", EventSeverity.INFO: "🔵"}
    for event in events:
        resolved_tag = " ✅" if event.resolved_at else ""
        header = f"{icon[event.severity]} [{event.category.value}] {event.message}{resolved_tag}"
        with st.expander(header):
            st.caption(f"Logged {event.created_at:%Y-%m-%d %H:%M:%S}")
            st.code(event.technical_detail or "(no technical detail)", language=None)

            if event.resolved_at:
                st.success(
                    f"Resolved by {event.resolved_by} on {event.resolved_at:%Y-%m-%d %H:%M:%S}"
                    + (f" — {event.resolution_note}" if event.resolution_note else "")
                )
            else:
                note = st.text_input("Resolution note (optional)", key=f"note_{event.id}")
                if st.button("Mark resolved", key=f"resolve_{event.id}"):
                    resolve_event(session, event, current_user, note or None)
                    session.commit()
                    st.rerun()

    nav1, _, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("⬅ Previous", disabled=st.session_state["logs_page"] <= 1, key="logs_prev"):
            st.session_state["logs_page"] -= 1
            st.rerun()
    with nav3:
        if st.button(
            "Next ➡", disabled=st.session_state["logs_page"] >= total_pages, key="logs_next"
        ):
            st.session_state["logs_page"] += 1
            st.rerun()
