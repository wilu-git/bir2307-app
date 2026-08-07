"""Logs tab: filterable event_logs viewer with a one-time resolve action."""

from __future__ import annotations

import streamlit as st

from app.core.logging_config import resolve_event, search_events
from app.core.models import EventCategory, EventLog, EventSeverity
from app.ui.components.cards import render_selectable_card

PAGE_SIZE = 25

_SEVERITY_VARIANT = {"info": "accent", "warning": "warning", "error": "error"}


def render_logs_tab(session, current_user, middle, right) -> None:
    with middle:
        st.subheader("Logs")
        col1, col2, col3 = st.columns(3)
        with col1:
            category_query = st.selectbox(
                "Category", options=["(all)"] + [c.value for c in EventCategory], key="logs_category"
            )
        with col2:
            severity_query = st.selectbox(
                "Severity", options=["(all)"] + [s.value for s in EventSeverity], key="logs_severity"
            )
        with col3:
            unresolved_only = st.checkbox("Unresolved only", value=True, key="logs_unresolved_only")

        st.session_state["logs_filters"] = {
            "category": category_query,
            "severity": severity_query,
            "unresolved_only": unresolved_only,
        }

        filters_key = (category_query, severity_query, unresolved_only)
        if st.session_state.get("logs_last_filters_key") != filters_key:
            st.session_state["logs_page"] = 1
            st.session_state["logs_last_filters_key"] = filters_key

        category_filter = EventCategory(category_query) if category_query != "(all)" else None
        severity_filter = EventSeverity(severity_query) if severity_query != "(all)" else None

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
            f"{total_count} matching log entr{'y' if total_count == 1 else 'ies'} — "
            f"page {st.session_state['logs_page']} of {total_pages}"
        )

        if not events:
            st.info("No log entries match these filters.")
        else:
            with st.container(height=420, key="middle_list"):
                for event in events:
                    title = event.message if len(event.message) <= 70 else event.message[:67] + "…"
                    if event.resolved_at:
                        title += " ✅"
                    clicked = render_selectable_card(
                        title=title,
                        subtitle=f"[{event.category.value}] · {event.created_at:%Y-%m-%d %H:%M:%S}",
                        badge=(event.severity.value, _SEVERITY_VARIANT[event.severity.value]),
                        is_selected=st.session_state["selected_log"] == event.id,
                        key=f"log_{event.id}",
                    )
                    if clicked:
                        st.session_state["selected_log"] = event.id
                        st.rerun()

            nav1, _, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button(
                    "⬅ Previous", disabled=st.session_state["logs_page"] <= 1, key="logs_prev"
                ):
                    st.session_state["logs_page"] -= 1
                    st.rerun()
            with nav3:
                if st.button(
                    "Next ➡",
                    disabled=st.session_state["logs_page"] >= total_pages,
                    key="logs_next",
                ):
                    st.session_state["logs_page"] += 1
                    st.rerun()

    with right:
        log_id = st.session_state["selected_log"]
        if not log_id:
            st.info("Select a log entry to see its details.")
            return
        event = session.get(EventLog, log_id)
        if event is None:
            st.warning("That log entry no longer exists.")
            st.session_state["selected_log"] = None
            return

        st.subheader(f"[{event.category.value}] {event.severity.value}")
        st.write(event.message)
        st.caption(f"Logged {event.created_at:%Y-%m-%d %H:%M:%S}")
        for label, value in (
            ("Upload batch", event.batch_id),
            ("Certificate", event.certificate_id),
            ("Transaction", event.transaction_id),
        ):
            if value is not None:
                st.caption(f"{label}: #{value}")

        st.divider()
        st.caption("Technical detail (developer-only — full, unmasked data):")
        st.code(event.technical_detail or "(no technical detail)", language=None)

        st.divider()
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
