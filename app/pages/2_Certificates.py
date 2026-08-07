"""Certificates page: group transactions into certificates, generate the
unsigned PDF, manage status transitions, and attach the scanned signed copy.

Thin by design — all business logic (grouping, status transitions, PDF
rendering) lives in app/core/; this file only wires widgets to it.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.config import settings
from app.core.auth import require_login
from app.core.certificates import group_ungrouped_transactions, transition_status
from app.core.db import SessionLocal, init_db
from app.core.logging_config import configure_logging, log_event
from app.core.models import Certificate, CertificateStatus, EventCategory, EventSeverity
from app.core.pdf_generator import generate_certificate_pdf
from app.core.security import mask_tin

configure_logging()
init_db()
current_user = require_login()

st.title("Certificates")

with SessionLocal() as session:
    if st.button("Group new transactions into certificates", type="primary"):
        touched = group_ungrouped_transactions(session)
        st.success(f"{len(touched)} certificate(s) created or updated.")

    status_filter = st.selectbox(
        "Filter by status",
        options=["(all)"] + [s.value for s in CertificateStatus],
    )
    query = session.query(Certificate)
    if status_filter != "(all)":
        query = query.filter(Certificate.status == status_filter)
    certificates = query.order_by(Certificate.id.desc()).all()

    st.caption(f"{len(certificates)} certificate(s)")

    for certificate in certificates:
        payee = certificate.payee
        header = (
            f"#{certificate.id} — {payee.registered_name} ({mask_tin(payee.tin)}) — "
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

            col_pdf, col_status, col_signed = st.columns(3)

            with col_pdf:
                if st.button("Generate/regenerate unsigned PDF", key=f"gen_{certificate.id}"):
                    try:
                        path = generate_certificate_pdf(
                            session, certificate, settings.generated_pdfs_dir
                        )
                        if certificate.status == CertificateStatus.DRAFT:
                            transition_status(
                                session,
                                certificate,
                                CertificateStatus.GENERATED,
                                current_user,
                                "PDF generated.",
                            )
                        log_event(
                            session,
                            category=EventCategory.PDF_GENERATION,
                            severity=EventSeverity.INFO,
                            message=f"Generated unsigned PDF for certificate #{certificate.id}.",
                            technical_detail=str(path),
                            certificate_id=certificate.id,
                        )
                        session.commit()
                        st.success(f"Saved to {path}")
                    except Exception as exc:
                        log_event(
                            session,
                            category=EventCategory.PDF_GENERATION,
                            severity=EventSeverity.ERROR,
                            message=f"Failed to generate PDF for certificate #{certificate.id}.",
                            technical_detail=repr(exc),
                            certificate_id=certificate.id,
                        )
                        session.commit()
                        st.error(f"PDF generation failed: {exc}")

                if certificate.pdf_unsigned_path and Path(certificate.pdf_unsigned_path).exists():
                    with open(certificate.pdf_unsigned_path, "rb") as f:
                        st.download_button(
                            "Download unsigned PDF",
                            f.read(),
                            file_name=Path(certificate.pdf_unsigned_path).name,
                            mime="application/pdf",
                            key=f"dl_{certificate.id}",
                        )

            with col_status:
                new_status = st.selectbox(
                    "Change status",
                    options=[s.value for s in CertificateStatus],
                    index=[s.value for s in CertificateStatus].index(certificate.status.value),
                    key=f"status_{certificate.id}",
                )
                note = st.text_input("Note (optional)", key=f"note_{certificate.id}")
                if st.button("Update status", key=f"update_{certificate.id}"):
                    transition_status(
                        session,
                        certificate,
                        CertificateStatus(new_status),
                        current_user,
                        note or None,
                    )
                    session.commit()
                    st.success(f"Status updated to {new_status}.")
                    st.rerun()

            with col_signed:
                signed_file = st.file_uploader(
                    "Upload scanned signed copy", type=["pdf"], key=f"signed_{certificate.id}"
                )
                if signed_file is not None and st.button(
                    "Attach signed copy", key=f"attach_{certificate.id}"
                ):
                    dest_dir = settings.generated_pdfs_dir / payee.tin.replace("/", "-")
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / f"{certificate.id}_signed.pdf"
                    dest.write_bytes(signed_file.getvalue())
                    certificate.pdf_signed_path = str(dest)
                    transition_status(
                        session,
                        certificate,
                        CertificateStatus.COMPLETED_SIGNED,
                        current_user,
                        "Signed copy uploaded.",
                    )
                    session.commit()
                    st.success("Signed copy attached; status set to completed_signed.")
                    st.rerun()

                if certificate.pdf_signed_path and Path(certificate.pdf_signed_path).exists():
                    st.caption(f"Signed copy on file: {Path(certificate.pdf_signed_path).name}")
