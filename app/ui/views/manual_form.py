"""Manual Form: a blank BIR 2307 that a human fills in by hand, field by
field, and renders straight onto the official template — no Payee,
Payor, Transaction, or Certificate row is ever created. This is a
one-off print path for cases the normal import/certificate pipeline
doesn't cover (a one-time payee never entered as a real record, a
correction typed straight onto a fresh copy, etc.), deliberately kept
separate from that pipeline rather than silently writing to the database
under the covers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import streamlit as st

from app.config import settings
from app.core.models import AtcCode, Payor
from app.core.pdf_generator import (
    MAX_ATC_LINES_PER_CERTIFICATE,
    LineItem,
    PartyFields,
    generate_manual_form_pdf,
)
from app.ui.components.preview import render_pdf_preview
from app.ui.layout import render_top_bar

_ROW_KEYS = ["desc", "atc", "m1", "m2", "m3", "tax"]


def _row_defaults(atc_options: list[str]) -> dict:
    return {"desc": "", "atc": atc_options[0] if atc_options else "", "m1": 0.0, "m2": 0.0, "m3": 0.0, "tax": 0.0}


def _to_decimal(value: float) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def render_manual_form_view(session, current_user: str) -> None:
    render_top_bar(session)

    st.markdown("### Manual Form")
    st.caption(
        "Fill in a blank BIR 2307 by hand and print it — nothing here is saved as a "
        "payee, transaction, or certificate record. For recurring payees, use the normal "
        "Excel import + Certificates flow instead; this page is for one-off, purely manual entry."
    )

    payor_default = session.query(Payor).first()
    atc_options = [a.code for a in session.query(AtcCode).order_by(AtcCode.code).all()]

    with st.container(border=True):
        st.markdown("**Period covered**")
        p1, p2 = st.columns(2)
        with p1:
            period_start = st.date_input("From", value=date.today().replace(month=1, day=1), key="manual_period_from")
        with p2:
            period_end = st.date_input("To", value=date.today(), key="manual_period_to")

    col_payee, col_payor = st.columns(2)
    with col_payee:
        with st.container(border=True):
            st.markdown("**Payee (Part I)**")
            payee_tin = st.text_input("TIN", placeholder="000-000-000-000", key="manual_payee_tin")
            payee_name = st.text_input("Registered name", key="manual_payee_name")
            payee_address = st.text_input("Registered address", key="manual_payee_address")
            payee_zip = st.text_input("ZIP code", key="manual_payee_zip")

    with col_payor:
        with st.container(border=True):
            st.markdown("**Payor (Part II)**")
            payor_tin = st.text_input(
                "TIN", value=payor_default.tin if payor_default else "", key="manual_payor_tin"
            )
            payor_name = st.text_input(
                "Registered name", value=payor_default.registered_name if payor_default else "", key="manual_payor_name"
            )
            payor_address = st.text_input(
                "Registered address", value=payor_default.address or "" if payor_default else "", key="manual_payor_address"
            )
            payor_zip = st.text_input(
                "ZIP code", value=payor_default.zip_code or "" if payor_default else "", key="manual_payor_zip"
            )

    with st.container(border=True):
        st.markdown("**Part III — Income payments & taxes withheld**")
        st.caption(f"Up to {MAX_ATC_LINES_PER_CERTIFICATE} line items, matching the printed form's row limit.")
        row_count = st.number_input(
            "Number of line items", min_value=1, max_value=MAX_ATC_LINES_PER_CERTIFICATE, value=1, step=1, key="manual_row_count"
        )

        line_items: list[LineItem] = []
        for i in range(int(row_count)):
            st.markdown(f"Line {i + 1}")
            r1, r2 = st.columns([2, 1])
            with r1:
                desc = st.text_input("Description", key=f"manual_row_{i}_desc")
            with r2:
                atc = st.selectbox(
                    "ATC code",
                    options=[""] + atc_options,
                    key=f"manual_row_{i}_atc",
                )
            m1, m2, m3, tax = st.columns(4)
            with m1:
                month1 = st.number_input("1st month (₱)", min_value=0.0, step=100.0, format="%.2f", key=f"manual_row_{i}_m1")
            with m2:
                month2 = st.number_input("2nd month (₱)", min_value=0.0, step=100.0, format="%.2f", key=f"manual_row_{i}_m2")
            with m3:
                month3 = st.number_input("3rd month (₱)", min_value=0.0, step=100.0, format="%.2f", key=f"manual_row_{i}_m3")
            with tax:
                tax_withheld = st.number_input(
                    "Tax withheld (₱)", min_value=0.0, step=10.0, format="%.2f", key=f"manual_row_{i}_tax"
                )
            if desc.strip() or atc or month1 or month2 or month3 or tax_withheld:
                line_items.append(
                    LineItem(
                        atc_code=atc or "",
                        description=desc.strip(),
                        month_amounts=(_to_decimal(month1), _to_decimal(month2), _to_decimal(month3)),
                        tax_withheld=_to_decimal(tax_withheld),
                    )
                )
            st.divider()

    missing = []
    if not payee_tin.strip():
        missing.append("Payee TIN")
    if not payee_name.strip():
        missing.append("Payee name")
    if not payor_tin.strip():
        missing.append("Payor TIN")
    if not payor_name.strip():
        missing.append("Payor name")
    if missing:
        st.warning("Fill in before generating: " + ", ".join(missing))

    if st.button("Generate PDF", type="primary", disabled=bool(missing)):
        path = generate_manual_form_pdf(
            period_start=period_start,
            period_end=period_end,
            payee=PartyFields(tin=payee_tin.strip(), name=payee_name.strip(), address=payee_address.strip(), zip_code=payee_zip.strip() or None),
            payor=PartyFields(tin=payor_tin.strip(), name=payor_name.strip(), address=payor_address.strip(), zip_code=payor_zip.strip() or None),
            line_items=line_items,
            output_dir=settings.generated_pdfs_dir,
        )
        st.session_state["manual_form_last_path"] = str(path)
        st.success(f"Generated {path.name}")

    if st.session_state.get("manual_form_last_path"):
        st.divider()
        render_pdf_preview(st.session_state["manual_form_last_path"], "Generated form", key_suffix="manual_form")
