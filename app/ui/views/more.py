"""More: low-frequency administrative functions behind a mini-nav —
Audit Log (real, migrated from the old Logs tab), Settings (real —
finally wires records.update_payor to a UI, previously README-only), and
honest placeholders for Users & Roles / Security / Backup, which have no
backend behind them yet (see the front-end redesign gap list).
"""

from __future__ import annotations

import streamlit as st

from app.core.logging_config import resolve_event, search_events
from app.core.mapping_profiles import delete_profile, list_profiles
from app.core.models import EventCategory, EventLog, EventSeverity, Payor
from app.core.records import PayorFields, update_payor
from app.ui.components.cards import status_badge
from app.ui.layout import render_top_bar
from app.ui.styles import SEVERITY_VARIANT

PAGE_SIZE = 25

_SECTIONS = [
    ("audit", "Audit Log", "Complete event history"),
    ("settings", "Settings", "Organization & preferences"),
    ("users", "Users & Roles", "Manage team access"),
    ("security", "Security", "Authentication & sessions"),
    ("backup", "Backup", "Data protection status"),
]


def _render_audit_log(session, current_user: str) -> None:
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
    st.caption(f"{total_count} matching log entr{'y' if total_count == 1 else 'ies'} — page {st.session_state['logs_page']} of {total_pages}")

    if not events:
        st.info("No log entries match these filters.")
        return

    for event in events:
        with st.container(border=True):
            title_col, badge_col = st.columns([4, 1])
            with title_col:
                st.markdown(f"**{event.message}**")
                st.caption(f"[{event.category.value}] · {event.created_at:%Y-%m-%d %H:%M:%S}")
            with badge_col:
                status_badge(event.severity.value, SEVERITY_VARIANT[event.severity.value])

            with st.expander("Details"):
                for label, value in (
                    ("Upload batch", event.batch_id),
                    ("Certificate", event.certificate_id),
                    ("Transaction", event.transaction_id),
                ):
                    if value is not None:
                        st.caption(f"{label}: #{value}")
                st.caption("Technical detail (developer-only):")
                st.code(event.technical_detail or "(none)", language=None)

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
        if st.button("Next ➡", disabled=st.session_state["logs_page"] >= total_pages, key="logs_next"):
            st.session_state["logs_page"] += 1
            st.rerun()


def _render_settings(session, current_user: str) -> None:
    payor = session.query(Payor).first()
    is_placeholder = payor is not None and payor.tin == "000-000-000-000"

    with st.container(border=True):
        st.markdown("**Payor Information**")
        if is_placeholder:
            st.warning("This is still the seeded placeholder — replace it before issuing real certificates.")
        with st.form("edit_payor_form"):
            tin = st.text_input("TIN", value=payor.tin)
            name = st.text_input("Registered name", value=payor.registered_name)
            address = st.text_input("Registered address", value=payor.address or "")
            zip_code = st.text_input("ZIP code", value=payor.zip_code or "")
            if st.form_submit_button("Save payor information", type="primary"):
                update_payor(
                    session,
                    payor,
                    PayorFields(tin=tin, registered_name=name, address=address or None, zip_code=zip_code or None),
                    current_user,
                )
                session.commit()
                st.success("Payor information updated.")
                st.rerun()

    st.write("")
    with st.container(border=True):
        st.markdown("**Mapping Profiles**")
        st.caption("Saved Excel column-mapping profiles, reusable across future imports.")
        profiles = list_profiles(session)
        if not profiles:
            st.caption("No saved profiles yet — save one from the import wizard's Map step.")
        for profile in profiles:
            col_a, col_b = st.columns([4, 1])
            col_a.write(f"**{profile.name}** · sheet: {profile.sheet_name or '(any)'} · {len(profile.mapping)} field(s) mapped")
            if col_b.button("Delete", key=f"delete_profile_{profile.id}"):
                delete_profile(session, profile.id)
                session.commit()
                st.rerun()

    st.write("")
    with st.container(border=True):
        st.markdown("**Certificate Preferences**")
        st.caption(
            "⚠️ Not yet implemented — the design spec references this section without defining "
            "concrete settings; there is nothing in the backend to configure here yet."
        )


def _render_placeholder(title: str, note: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(f"⚠️ Not yet implemented — {note}")


def render_more_view(session, current_user: str) -> None:
    render_top_bar(session)

    nav_col, content_col = st.columns([1, 4], gap="medium")
    with nav_col:
        for key, label, _desc in _SECTIONS:
            active = st.session_state["more_section"] == key
            if st.button(label, key=f"more_{key}", use_container_width=True, type="primary" if active else "secondary"):
                st.session_state["more_section"] = key
                st.rerun()

    with content_col:
        section = st.session_state["more_section"]
        label = next(s[1] for s in _SECTIONS if s[0] == section)
        desc = next(s[2] for s in _SECTIONS if s[0] == section)
        st.markdown(f"### {label}")
        st.caption(desc)

        if section == "audit":
            _render_audit_log(session, current_user)
        elif section == "settings":
            _render_settings(session, current_user)
        elif section == "users":
            _render_placeholder(
                "Users & Roles",
                "the app has a single shared password and one hardcoded user identity today — "
                "individual accounts and Preparer/Reviewer/Administrator roles are a P0 gap (security-sensitive).",
            )
        elif section == "security":
            _render_placeholder(
                "Security",
                "session management, 2FA, and password policy depend on the Users & Roles work above.",
            )
        elif section == "backup":
            with st.container(border=True):
                st.markdown("**Backup Status**")
                st.info(
                    "Backups are manual today — there is no automated backup job. Back up "
                    "`data/bir2307.db` and `data/generated_pdfs/` regularly; see README.md."
                )
