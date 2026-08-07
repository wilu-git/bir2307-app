"""Certificates tab: group transactions into certificates, generate the
unsigned PDF, manage status transitions, and attach the scanned signed copy.

Middle panel lists/filters certificates; right panel renders the shared
`render_document_preview` (also used by the Search tab) plus the
certificate-mutating actions, which deliberately live here rather than in
the shared preview function so Search's reuse of it stays a pure viewer.
"""

from __future__ import annotations

import streamlit as st

from app.config import settings
from app.core.certificates import group_ungrouped_transactions, transition_status
from app.core.logging_config import log_event
from app.core.models import Certificate, CertificateStatus, EventCategory, EventSeverity
from app.core.pdf_generator import generate_certificate_pdf
from app.core.security import mask_tin
from app.ui.components.cards import render_selectable_card
from app.ui.components.preview import STATUS_BADGE_VARIANT, render_document_preview


def render_certificates_tab(session, current_user, middle, right) -> None:
    with middle:
        st.subheader("Certificates")
        if st.button(
            "Group new transactions into certificates", type="primary", use_container_width=True
        ):
            touched = group_ungrouped_transactions(session)
            st.success(f"{len(touched)} certificate(s) created or updated.")

        status_filter = st.selectbox(
            "Filter by status",
            options=["(all)"] + [s.value for s in CertificateStatus],
            key="cert_status_filter",
        )
        query = session.query(Certificate)
        if status_filter != "(all)":
            query = query.filter(Certificate.status == status_filter)
        certificates = query.order_by(Certificate.id.desc()).all()
        st.caption(f"{len(certificates)} certificate(s)")

        with st.container(height=520, key="middle_list"):
            for certificate in certificates:
                payee = certificate.payee
                clicked = render_selectable_card(
                    title=f"#{certificate.id} — {payee.registered_name}",
                    subtitle=(
                        f"{mask_tin(payee.tin)} · {certificate.period_start:%Y-%m-%d} to "
                        f"{certificate.period_end:%Y-%m-%d}"
                    ),
                    badge=(
                        certificate.status.value,
                        STATUS_BADGE_VARIANT.get(certificate.status.value, "neutral"),
                    ),
                    is_selected=st.session_state["selected_certificate"] == certificate.id,
                    key=f"cert_{certificate.id}",
                )
                if clicked:
                    st.session_state["selected_certificate"] = certificate.id
                    st.rerun()

    with right:
        cert_id = st.session_state["selected_certificate"]
        if not cert_id:
            st.info("Select a certificate to see its details.")
            return
        certificate = session.get(Certificate, cert_id)
        if certificate is None:
            st.warning("That certificate no longer exists.")
            st.session_state["selected_certificate"] = None
            return

        render_document_preview(certificate)

        st.divider()
        st.subheader("Actions")
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
                st.success(f"Status updated to {new_status}.")
                st.rerun()

        with col_signed:
            signed_file = st.file_uploader(
                "Upload scanned signed copy", type=["pdf"], key=f"signed_{certificate.id}"
            )
            if signed_file is not None and st.button(
                "Attach signed copy", key=f"attach_{certificate.id}"
            ):
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
                st.success("Signed copy attached; status set to completed_signed.")
                st.rerun()
