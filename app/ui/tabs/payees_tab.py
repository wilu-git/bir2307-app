"""Payees tab: the unified browse + search + act screen.

Replaces the old Certificates tab and Search tab. The list column is a
searchable/filterable list of payees (name, TIN, quarter, status); the
detail column shows the selected payee's certificates as expandable cards,
each with the same preview + actions the old Certificates tab offered.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.core.certificates import group_ungrouped_transactions
from app.core.models import CertificateStatus
from app.core.payees import get_certificates_for_payee, list_payees_with_summary, list_quarter_options, quarter_bounds
from app.core.security import mask_tin
from app.ui.components.cards import render_selectable_card
from app.ui.components.certificate_actions import render_certificate_actions
from app.ui.components.preview import STATUS_BADGE_VARIANT, render_document_preview


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year} Q{quarter}"


def render_payees_tab(session, current_user, list_col, detail_col) -> None:
    with list_col:
        st.subheader("Payees")
        if st.button(
            "Group new transactions into certificates", type="primary", use_container_width=True
        ):
            touched = group_ungrouped_transactions(session)
            st.success(f"{len(touched)} certificate(s) created or updated.")

        c1, c2 = st.columns(2)
        with c1:
            name_query = st.text_input(
                "Payee name contains", placeholder="e.g. Shangri-La", key="payee_name"
            )
        with c2:
            tin_query = st.text_input(
                "TIN contains", placeholder="digits only or with dashes", key="payee_tin"
            )

        quarter_options = list_quarter_options()
        quarter_labels = ["(all)"] + [_quarter_label(y, q) for y, q in quarter_options]
        quarter_choice = st.selectbox("Quarter", options=quarter_labels, key="payee_quarter")

        date_range: tuple = ()
        with st.expander("Advanced date filter"):
            date_range = st.date_input(
                "Period overlaps date range",
                value=(),
                format="YYYY-MM-DD",
                key="payee_date_range",
                help="Only used when Quarter above is set to (all).",
            )

        status_query = st.selectbox(
            "Status",
            options=["(all)"] + [s.value for s in CertificateStatus],
            key="payee_status",
        )

        st.session_state["payee_filters"] = {
            "name": name_query,
            "tin": tin_query,
            "quarter": quarter_choice,
            "date_range": date_range,
            "status": status_query,
        }

        filters_key = (name_query, tin_query, quarter_choice, str(date_range), status_query)
        if st.session_state.get("payee_last_filters_key") != filters_key:
            st.session_state["selected_payee"] = None
            st.session_state["selected_certificate"] = None
            st.session_state["payee_last_filters_key"] = filters_key

        if quarter_choice != "(all)":
            year, quarter = quarter_options[quarter_labels.index(quarter_choice) - 1]
            period_from, period_to = quarter_bounds(year, quarter)
        elif len(date_range) >= 1:
            period_from = datetime.combine(date_range[0], datetime.min.time())
            period_to = (
                datetime.combine(date_range[1], datetime.min.time())
                if len(date_range) == 2
                else None
            )
        else:
            period_from = period_to = None

        status_filter = CertificateStatus(status_query) if status_query != "(all)" else None

        summaries = list_payees_with_summary(
            session,
            name=name_query,
            tin=tin_query,
            period_from=period_from,
            period_to=period_to,
            status=status_filter,
        )
        st.caption(f"{len(summaries)} payee(s)")

        with st.container(height=520, key="payees_list"):
            for summary in summaries:
                payee = summary.payee
                badge = None
                if summary.latest_status is not None:
                    badge = (
                        summary.latest_status.value,
                        STATUS_BADGE_VARIANT.get(summary.latest_status.value, "neutral"),
                    )
                clicked = render_selectable_card(
                    title=payee.registered_name,
                    subtitle=(
                        f"{mask_tin(payee.tin)} · {summary.matching_certificate_count} matching "
                        f"(of {summary.certificate_count})"
                    ),
                    badge=badge,
                    is_selected=st.session_state["selected_payee"] == payee.id,
                    key=f"payee_{payee.id}",
                    list_id="payees",
                )
                if clicked:
                    st.session_state["selected_payee"] = payee.id
                    st.session_state["selected_certificate"] = None
                    st.rerun()

    with detail_col:
        payee_id = st.session_state["selected_payee"]
        if not payee_id:
            st.info("Select a payee to see their certificates.")
            return

        filters = st.session_state["payee_filters"]
        quarter_options = list_quarter_options()
        quarter_labels = ["(all)"] + [_quarter_label(y, q) for y, q in quarter_options]
        if filters["quarter"] != "(all)":
            year, quarter = quarter_options[quarter_labels.index(filters["quarter"]) - 1]
            period_from, period_to = quarter_bounds(year, quarter)
        elif len(filters["date_range"]) >= 1:
            period_from = datetime.combine(filters["date_range"][0], datetime.min.time())
            period_to = (
                datetime.combine(filters["date_range"][1], datetime.min.time())
                if len(filters["date_range"]) == 2
                else None
            )
        else:
            period_from = period_to = None
        status_filter = (
            CertificateStatus(filters["status"]) if filters["status"] != "(all)" else None
        )

        certificates = get_certificates_for_payee(
            session, payee_id, period_from=period_from, period_to=period_to, status=status_filter
        )
        if not certificates:
            st.warning("This payee has no certificates matching the current filters.")
            return

        payee = certificates[0].payee
        st.subheader(payee.registered_name)
        st.caption(f"{mask_tin(payee.tin)} · {payee.tax_type.value} · {payee.address or 'no address on file'}")
        st.caption(f"{len(certificates)} certificate(s) matching current filters")

        selected_cert_id = st.session_state["selected_certificate"]
        for i, certificate in enumerate(certificates):
            # Auto-expand whichever certificate an action was last taken on
            # (see certificate_actions.py); with nothing selected yet,
            # default to the most recent certificate (first in the list).
            is_open = selected_cert_id == certificate.id or (
                selected_cert_id is None and i == 0
            )
            label = (
                f"#{certificate.id} · {certificate.period_start:%Y-%m-%d} to "
                f"{certificate.period_end:%Y-%m-%d} · {certificate.status.value}"
            )
            with st.expander(label, expanded=is_open):
                render_document_preview(certificate)
                st.divider()
                render_certificate_actions(session, certificate, current_user)
