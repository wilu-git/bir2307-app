"""Payees: recurring payee entities and their certificate history. A
row's drawer (`st.dialog`) carries Overview/Transactions/Certificates/
History tabs — Overview's edit form is the first UI ever wired to
`records.update_payee` (it previously only had a backend function, no
screen at all).
"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from app.config import settings
from app.core.certificates import transition_status
from app.core.logging_config import log_event
from app.core.models import CertificateStatus, EventCategory, EventSeverity, TaxType
from app.core.payees import get_events_for_payee, get_transactions_for_payee, list_payees_with_summary
from app.core.pdf_generator import generate_certificate_pdf
from app.core.records import DuplicateTinError, PayeeFields, update_payee
from app.core.security import mask_tin
from app.ui.components.cards import status_badge
from app.ui.layout import render_top_bar
from app.ui.state import current_quarter_bounds
from app.ui.styles import CERT_STATUS_VARIANT

_NON_DIGITS = re.compile(r"\D+")


def _digits_only(value: str) -> str:
    return _NON_DIGITS.sub("", value)


_STATUS_LABEL = {
    "draft": "Draft",
    "generated": "Generated",
    "forwarded": "Forwarded",
    "completed_signed": "Signed",
    "void": "Void",
}


def _payee_is_active_this_quarter(payee, period_start, period_end) -> bool:
    """Not a stored flag — Payee has no such column. Derived here as "has
    at least one certificate whose period overlaps the selected quarter",
    a UI-only convenience, not a persisted business fact."""
    return any(c.period_end >= period_start and c.period_start <= period_end for c in payee.certificates)


def _outstanding_count(payee) -> int:
    return sum(
        1
        for c in payee.certificates
        if c.status not in (CertificateStatus.COMPLETED_SIGNED, CertificateStatus.VOID)
    )


def _last_certificate_label(payee) -> str:
    if not payee.certificates:
        return "—"
    latest = max(payee.certificates, key=lambda c: c.id)
    return f"{latest.period_start:%Y}-Q{(latest.period_start.month - 1) // 3 + 1}"


@st.dialog("Payee", width="large")
def _payee_drawer(session, payee_id: int, current_user: str) -> None:
    from app.core.models import Payee

    payee = session.get(Payee, payee_id)
    if payee is None:
        st.warning("This payee no longer exists.")
        return

    st.markdown(f"### {payee.registered_name}")
    st.caption(f"{payee.tin} · {payee.address or 'no address on file'}")

    tab_overview, tab_txns, tab_certs, tab_history = st.tabs(
        ["Overview", "Transactions", "Certificates", "History"]
    )

    with tab_overview:
        c1, c2 = st.columns(2)
        c1.metric("Total certificates", len(payee.certificates))
        c2.metric("Outstanding", _outstanding_count(payee))

        with st.expander("Edit payee record"):
            with st.form(key=f"edit_payee_{payee.id}"):
                tin = st.text_input("TIN", value=payee.tin)
                name = st.text_input("Registered name", value=payee.registered_name)
                address = st.text_input("Address", value=payee.address or "")
                zip_code = st.text_input("ZIP code", value=payee.zip_code or "")
                tax_type = st.selectbox(
                    "Tax type",
                    options=[t.value for t in TaxType],
                    index=[t.value for t in TaxType].index(payee.tax_type.value),
                )
                if st.form_submit_button("Save changes", type="primary"):
                    try:
                        update_payee(
                            session,
                            payee,
                            PayeeFields(
                                tin=tin,
                                registered_name=name,
                                address=address or None,
                                zip_code=zip_code or None,
                                tax_type=TaxType(tax_type),
                            ),
                            current_user,
                        )
                        session.commit()
                        st.success("Payee record updated.")
                        st.rerun()
                    except DuplicateTinError as exc:
                        session.rollback()
                        st.error(str(exc))

    with tab_txns:
        transactions = get_transactions_for_payee(session, payee.id)
        if not transactions:
            st.caption("No transactions recorded for this payee.")
        for txn in transactions[:50]:
            st.markdown(f"**{txn.reference_no}** · {txn.atc_code}")
            date_label = f"{txn.invoice_date:%Y-%m-%d}" if txn.invoice_date else "no date"
            st.caption(f"{date_label} · Gross ₱{txn.gross_amount:,.2f} · EWT ₱{txn.tax_withheld:,.2f}")
            st.write("")
        if len(transactions) > 50:
            st.caption(f"Showing 50 of {len(transactions)} transactions.")

    with tab_certs:
        certs = sorted(payee.certificates, key=lambda c: c.id, reverse=True)
        if not certs:
            st.caption("No certificates yet.")
        for cert in certs:
            col_a, col_b, col_c = st.columns([3, 1, 1.6])
            with col_a:
                st.markdown(f"#{cert.id} · {cert.period_start:%Y-%m-%d} to {cert.period_end:%Y-%m-%d}")
                st.caption(f"₱{(cert.total_gross - cert.total_tax_withheld):,.2f}")
            with col_b:
                status_badge(_STATUS_LABEL[cert.status.value], CERT_STATUS_VARIANT[cert.status.value])
            with col_c:
                if st.button("Generate PDF", key=f"payee_gen_{cert.id}", use_container_width=True):
                    try:
                        path = generate_certificate_pdf(session, cert, settings.generated_pdfs_dir)
                        if cert.status == CertificateStatus.DRAFT:
                            transition_status(session, cert, CertificateStatus.GENERATED, current_user, "PDF generated.")
                        log_event(
                            session,
                            category=EventCategory.PDF_GENERATION,
                            severity=EventSeverity.INFO,
                            message=f"Generated unsigned PDF for certificate #{cert.id}.",
                            technical_detail=str(path),
                            certificate_id=cert.id,
                        )
                        session.commit()
                        st.success(f"Saved to {path}")
                        st.rerun()
                    except Exception as exc:
                        log_event(
                            session,
                            category=EventCategory.PDF_GENERATION,
                            severity=EventSeverity.ERROR,
                            message=f"Failed to generate PDF for certificate #{cert.id}.",
                            technical_detail=repr(exc),
                            certificate_id=cert.id,
                        )
                        session.commit()
                        st.error(f"PDF generation failed: {exc}")

    with tab_history:
        events = get_events_for_payee(session, payee.id)
        if not events:
            st.caption("No recorded activity for this payee.")
        for event in events[:50]:
            st.markdown(f"**{event.message}**")
            st.caption(f"{event.created_at:%Y-%m-%d %H:%M} · {event.category.value} · {event.severity.value}")
            st.write("")


def render_payees_view(session, current_user: str) -> None:
    render_top_bar(session)

    st.markdown("### Payees")
    st.caption("Recurring payee entities and their certificate history.")

    search = st.text_input(
        "Search payees",
        value=st.session_state["payees_search"],
        placeholder="Search payees or TIN…",
        label_visibility="collapsed",
        key="payees_search_input",
    )
    st.session_state["payees_search"] = search

    all_summaries = list_payees_with_summary(session)
    if search.strip():
        # list_payees_with_summary ANDs name/tin — a single search box needs OR.
        needle = search.strip().lower()
        needle_digits = _digits_only(search)
        summaries = [
            s
            for s in all_summaries
            if needle in s.payee.registered_name.lower() or needle_digits in _digits_only(s.payee.tin)
        ]
    else:
        summaries = all_summaries

    if not summaries:
        st.info("No payees found.")
        return

    period_start, period_end = current_quarter_bounds()
    st.caption(f"{len(summaries)} payee(s)")

    rows = []
    for s in summaries:
        p = s.payee
        rows.append(
            {
                "Payee": p.registered_name,
                "TIN": mask_tin(p.tin),
                "Certificates": s.certificate_count,
                "Last Certificate": _last_certificate_label(p),
                "Outstanding": _outstanding_count(p),
                "Active this quarter": "Yes" if _payee_is_active_this_quarter(p, period_start, period_end) else "No",
            }
        )
    df = pd.DataFrame(rows)

    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="payees_table",
    )
    selected_rows = event.selection["rows"] if event and event.selection else []
    if selected_rows:
        payee = summaries[selected_rows[0]].payee
        if st.button(f"Open {payee.registered_name} →", key="open_payee_drawer", type="primary"):
            st.session_state["selected_payee_id"] = payee.id
            _payee_drawer(session, payee.id, current_user)
