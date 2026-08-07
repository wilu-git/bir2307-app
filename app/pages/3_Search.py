"""Search & management dashboard: combinable filters over certificates by
payee name, TIN, period, and status, with pagination and quick view-only
actions (download PDFs) directly from the result list.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from app.core.auth import require_login
from app.core.db import SessionLocal, init_db
from app.core.logging_config import configure_logging
from app.core.models import CertificateStatus
from app.core.search import search_certificates
from app.core.security import mask_tin

configure_logging()
init_db()
require_login()

st.title("Search")

PAGE_SIZE = 20

col1, col2 = st.columns(2)
with col1:
    name_query = st.text_input("Payee name contains", placeholder="e.g. Shangri-La")
    tin_query = st.text_input("TIN contains", placeholder="digits only or with dashes")
with col2:
    date_range = st.date_input("Period overlaps date range", value=(), format="YYYY-MM-DD")
    status_query = st.selectbox("Status", options=["(all)"] + [s.value for s in CertificateStatus])

if "search_page" not in st.session_state:
    st.session_state["search_page"] = 1

# Any filter change should reset back to page 1, not strand the user deep
# in a page number that may no longer have results.
filters_key = (name_query, tin_query, str(date_range), status_query)
if st.session_state.get("last_filters_key") != filters_key:
    st.session_state["search_page"] = 1
    st.session_state["last_filters_key"] = filters_key

period_from = datetime.combine(date_range[0], datetime.min.time()) if len(date_range) >= 1 else None
period_to = datetime.combine(date_range[1], datetime.min.time()) if len(date_range) == 2 else None
status_filter = CertificateStatus(status_query) if status_query != "(all)" else None

with SessionLocal() as session:
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
        f"{result.total_count} matching certificate(s) — page {st.session_state['search_page']} of {total_pages}"
    )

    if not result.certificates:
        st.info(
            "No certificates match these filters. Try loosening a filter or clearing the search."
        )
    else:
        for certificate in result.certificates:
            payee = certificate.payee
            header = (
                f"{payee.registered_name} ({mask_tin(payee.tin)}) — "
                f"{certificate.period_start:%Y-%m-%d} to {certificate.period_end:%Y-%m-%d} — "
                f"{certificate.status.value}"
            )
            with st.expander(header):
                c1, c2, c3 = st.columns(3)
                c1.metric("Total gross", f"₱{certificate.total_gross:,.2f}")
                c2.metric("Total tax withheld", f"₱{certificate.total_tax_withheld:,.2f}")
                c3.metric("Status", certificate.status.value)
                st.write(f"**Full TIN:** {payee.tin}")
                st.write(f"**Address:** {payee.address or '—'}")

                if certificate.pdf_unsigned_path and Path(certificate.pdf_unsigned_path).exists():
                    with open(certificate.pdf_unsigned_path, "rb") as f:
                        st.download_button(
                            "Download unsigned PDF",
                            f.read(),
                            file_name=Path(certificate.pdf_unsigned_path).name,
                            mime="application/pdf",
                            key=f"search_dl_unsigned_{certificate.id}",
                        )
                if certificate.pdf_signed_path and Path(certificate.pdf_signed_path).exists():
                    with open(certificate.pdf_signed_path, "rb") as f:
                        st.download_button(
                            "Download signed copy",
                            f.read(),
                            file_name=Path(certificate.pdf_signed_path).name,
                            mime="application/pdf",
                            key=f"search_dl_signed_{certificate.id}",
                        )

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("⬅ Previous", disabled=st.session_state["search_page"] <= 1):
            st.session_state["search_page"] -= 1
            st.rerun()
    with nav3:
        if st.button("Next ➡", disabled=st.session_state["search_page"] >= total_pages):
            st.session_state["search_page"] += 1
            st.rerun()
