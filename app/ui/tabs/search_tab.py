"""Search tab: combinable filters over certificates, view-only.

The right panel calls the exact same `render_document_preview` used by the
Certificates tab (search results are certificates) — no separate PDF
rendering implementation, no mutating actions here.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.core.models import Certificate, CertificateStatus
from app.core.search import search_certificates
from app.core.security import mask_tin
from app.ui.components.cards import render_selectable_card
from app.ui.components.preview import STATUS_BADGE_VARIANT, render_document_preview

PAGE_SIZE = 20


def render_search_tab(session, middle, right) -> None:
    with middle:
        st.subheader("Search")
        col1, col2 = st.columns(2)
        with col1:
            name_query = st.text_input(
                "Payee name contains", placeholder="e.g. Shangri-La", key="search_name"
            )
            tin_query = st.text_input(
                "TIN contains", placeholder="digits only or with dashes", key="search_tin"
            )
        with col2:
            date_range = st.date_input(
                "Period overlaps date range", value=(), format="YYYY-MM-DD", key="search_date_range"
            )
            status_query = st.selectbox(
                "Status",
                options=["(all)"] + [s.value for s in CertificateStatus],
                key="search_status",
            )

        st.session_state["search_query"] = {
            "name": name_query,
            "tin": tin_query,
            "date_range": date_range,
            "status": status_query,
        }

        filters_key = (name_query, tin_query, str(date_range), status_query)
        if st.session_state.get("search_last_filters_key") != filters_key:
            st.session_state["search_page"] = 1
            st.session_state["search_last_filters_key"] = filters_key

        period_from = (
            datetime.combine(date_range[0], datetime.min.time()) if len(date_range) >= 1 else None
        )
        period_to = (
            datetime.combine(date_range[1], datetime.min.time()) if len(date_range) == 2 else None
        )
        status_filter = CertificateStatus(status_query) if status_query != "(all)" else None

        result = search_certificates(
            session,
            name=name_query,
            tin=tin_query,
            period_from=period_from,
            period_to=period_to,
            status=status_filter,
            page=st.session_state["search_page"],
            page_size=PAGE_SIZE,
        )
        total_pages = max(1, (result.total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        st.caption(
            f"{result.total_count} matching certificate(s) — "
            f"page {st.session_state['search_page']} of {total_pages}"
        )

        if not result.certificates:
            st.info(
                "No certificates match these filters. Try loosening a filter or clearing the search."
            )
        else:
            with st.container(height=420, key="middle_list"):
                for certificate in result.certificates:
                    payee = certificate.payee
                    clicked = render_selectable_card(
                        title=payee.registered_name,
                        subtitle=(
                            f"{mask_tin(payee.tin)} · {certificate.period_start:%Y-%m-%d} to "
                            f"{certificate.period_end:%Y-%m-%d}"
                        ),
                        badge=(
                            certificate.status.value,
                            STATUS_BADGE_VARIANT.get(certificate.status.value, "neutral"),
                        ),
                        is_selected=st.session_state["selected_search_result"] == certificate.id,
                        key=f"searchres_{certificate.id}",
                    )
                    if clicked:
                        st.session_state["selected_search_result"] = certificate.id
                        st.rerun()

            nav1, _, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button(
                    "⬅ Previous", disabled=st.session_state["search_page"] <= 1, key="search_prev"
                ):
                    st.session_state["search_page"] -= 1
                    st.rerun()
            with nav3:
                if st.button(
                    "Next ➡",
                    disabled=st.session_state["search_page"] >= total_pages,
                    key="search_next",
                ):
                    st.session_state["search_page"] += 1
                    st.rerun()

    with right:
        result_id = st.session_state["selected_search_result"]
        if not result_id:
            st.info("Select a search result to see its details.")
            return
        certificate = session.get(Certificate, result_id)
        if certificate is None:
            st.warning("That certificate no longer exists.")
            st.session_state["selected_search_result"] = None
            return
        render_document_preview(certificate)
