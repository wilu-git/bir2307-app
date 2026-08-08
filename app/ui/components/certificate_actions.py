"""Certificate-mutating actions: generate PDF, change status, attach signed
copy. Extracted from the old Certificates tab so it can be rendered once per
expanded certificate in the Payees tab's detail pane, instead of once for a
single globally-selected certificate.
"""

from __future__ import annotations

import streamlit as st

from app.config import settings
from app.core.certificates import transition_status
from app.core.logging_config import log_event
from app.core.models import CertificateStatus, EventCategory, EventSeverity
from app.core.pdf_generator import generate_certificate_pdf


def render_certificate_actions(session, certificate, current_user: str) -> None:
    """Renders the generate/status/signed-copy controls for one certificate.

    Each action sets `selected_certificate` to this certificate's id right
    before its `st.rerun()`, so the Payees tab's detail pane keeps this
    certificate's expander open across the rerun instead of collapsing it.
    """
    st.subheader("Actions")
    col_pdf, col_status, col_signed = st.columns(3)

    with col_pdf:
        if st.button("Generate/regenerate unsigned PDF", key=f"gen_{certificate.id}"):
            try:
                path = generate_certificate_pdf(session, certificate, settings.generated_pdfs_dir)
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
                st.session_state["selected_certificate"] = certificate.id
                st.success(f"Saved to {path}")
                st.rerun()
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
                session, certificate, CertificateStatus(new_status), current_user, note or None
            )
            session.commit()
            st.session_state["selected_certificate"] = certificate.id
            st.success(f"Status updated to {new_status}.")
            st.rerun()

    with col_signed:
        signed_file = st.file_uploader(
            "Upload scanned signed copy", type=["pdf"], key=f"signed_{certificate.id}"
        )
        if signed_file is not None and st.button("Attach signed copy", key=f"attach_{certificate.id}"):
            dest_dir = settings.generated_pdfs_dir / certificate.payee.tin.replace("/", "-")
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
            st.session_state["selected_certificate"] = certificate.id
            st.success("Signed copy attached; status set to completed_signed.")
            st.rerun()
