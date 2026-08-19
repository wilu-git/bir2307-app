"""Certificates: the main certificate workspace — table + bulk actions +
a detail "drawer" (an `st.dialog`, Streamlit has no true slide-out panel).
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd
import streamlit as st

from app.core.certificates import bulk_transition_status, transition_status
from app.core.logging_config import log_event
from app.core.models import CertificateStatus, EventCategory, EventSeverity, StatusLog
from app.core.pdf_generator import MAX_ATC_LINES_PER_CERTIFICATE, count_distinct_atc_codes, generate_certificate_pdf
from app.core.search import search_certificates
from app.core.security import mask_tin
from app.ui.components.cards import status_badge
from app.ui.components.preview import render_certificate_metrics, render_pdf_preview
from app.ui.layout import render_top_bar
from app.ui.state import current_quarter_bounds
from app.ui.styles import CERT_STATUS_VARIANT, page_tokens

_NON_DIGITS = re.compile(r"\D+")


def _digits_only(value: str) -> str:
    return _NON_DIGITS.sub("", value)


_STATUS_OPTIONS = ["(all)"] + [s.value for s in CertificateStatus]
_STATUS_LABEL = {
    "draft": "Draft",
    "generated": "Generated",
    "forwarded": "Forwarded",
    "completed_signed": "Signed",
    "void": "Void",
}


def _amount_paid(cert) -> float:
    return float(cert.total_gross - cert.total_tax_withheld)


@st.dialog("Certificate", width="large")
def _certificate_drawer(session, certificate_id: int, current_user: str) -> None:
    from app.core.models import Certificate

    cert = session.get(Certificate, certificate_id)
    if cert is None:
        st.warning("This certificate no longer exists.")
        return
    payee = cert.payee

    st.markdown(f"### {payee.registered_name}")
    meta_col, badge_col = st.columns([3, 1])
    with meta_col:
        st.caption(
            f"{mask_tin(payee.tin)} · {cert.period_start:%Y-%m-%d} to {cert.period_end:%Y-%m-%d} · "
            f"Certificate #{cert.id}"
        )
    with badge_col:
        status_badge(_STATUS_LABEL[cert.status.value], CERT_STATUS_VARIANT[cert.status.value])

    if count_distinct_atc_codes(session, cert) > MAX_ATC_LINES_PER_CERTIFICATE:
        st.warning(
            f"This certificate has more than {MAX_ATC_LINES_PER_CERTIFICATE} distinct ATC codes — "
            "rows will overlap on the printed PDF. Review before generating."
        )

    tab_summary, tab_timeline, tab_actions = st.tabs(["Summary", "Timeline", "Actions"])

    with tab_summary:
        render_certificate_metrics(cert)
        st.divider()
        render_pdf_preview(cert.pdf_unsigned_path, "Unsigned PDF", key_suffix=f"unsigned_{cert.id}")
        if cert.pdf_signed_path:
            st.divider()
            render_pdf_preview(cert.pdf_signed_path, "Signed copy", key_suffix=f"signed_{cert.id}")

    with tab_timeline:
        history = (
            session.query(StatusLog)
            .filter_by(certificate_id=cert.id)
            .order_by(StatusLog.changed_at)
            .all()
        )
        if not history:
            st.caption("No status changes recorded yet.")
        for entry in history:
            st.markdown(f"**{_STATUS_LABEL.get(entry.new_status, entry.new_status)}**")
            st.caption(f"{entry.changed_at:%Y-%m-%d %H:%M} · by {entry.changed_by}")
            if entry.note:
                st.caption(f"Note: {entry.note}")
            st.write("")

    with tab_actions:
        st.markdown("**Generate PDF**")
        if st.button("Generate/regenerate unsigned PDF", key=f"gen_{cert.id}"):
            try:
                from app.config import settings

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

        st.divider()
        st.markdown("**Change status**")
        new_status = st.selectbox(
            "New status",
            options=[s.value for s in CertificateStatus],
            index=[s.value for s in CertificateStatus].index(cert.status.value),
            key=f"status_{cert.id}",
            label_visibility="collapsed",
        )
        note = st.text_input("Note (optional)", key=f"note_{cert.id}")
        if st.button("Update status", key=f"update_{cert.id}"):
            transition_status(session, cert, CertificateStatus(new_status), current_user, note or None)
            session.commit()
            st.success(f"Status updated to {new_status}.")
            st.rerun()
        if cert.status != CertificateStatus.VOID and st.button(
            "Void this certificate", key=f"void_{cert.id}"
        ):
            transition_status(session, cert, CertificateStatus.VOID, current_user, "Voided from drawer.")
            session.commit()
            st.success("Certificate voided.")
            st.rerun()

        st.divider()
        st.markdown("**Signed copy**")
        if cert.pdf_signed_path:
            st.success("Signed copy received.")
        signed_file = st.file_uploader("Upload scanned signed copy", type=["pdf"], key=f"signed_{cert.id}")
        if signed_file is not None and st.button("Attach signed copy", key=f"attach_{cert.id}"):
            from app.config import settings

            dest_dir = settings.generated_pdfs_dir / cert.payee.tin.replace("/", "-")
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{cert.id}_signed.pdf"
            dest.write_bytes(signed_file.getvalue())
            cert.pdf_signed_path = str(dest)
            transition_status(session, cert, CertificateStatus.COMPLETED_SIGNED, current_user, "Signed copy uploaded.")
            session.commit()
            st.success("Signed copy attached; status set to completed_signed.")
            st.rerun()


def render_certificates_view(session, current_user: str) -> None:
    render_top_bar(session)
    t = page_tokens(st.session_state["theme"])

    header_col, export_col = st.columns([4, 1])
    with header_col:
        st.markdown("### Certificates")
        st.caption("Prepare, review, and track BIR 2307 certificates.")
    with export_col:
        st.button("Export", disabled=True, use_container_width=True, help="Not yet available — see gap list.")

    filters = st.session_state["certificates_filters"]
    search_col, status_col = st.columns([3, 1.4])
    with search_col:
        search = st.text_input(
            "Search certificates",
            value=filters["search"],
            placeholder="Search by payee name or TIN…",
            label_visibility="collapsed",
            key="cert_search",
        )
    with status_col:
        status = st.selectbox(
            "Status",
            options=_STATUS_OPTIONS,
            index=_STATUS_OPTIONS.index(filters["status"]) if filters["status"] in _STATUS_OPTIONS else 0,
            label_visibility="collapsed",
            key="cert_status_filter",
        )
    st.session_state["certificates_filters"] = {"search": search, "status": status}

    period_start, period_end = current_quarter_bounds()
    status_filter = CertificateStatus(status) if status != "(all)" else None
    # search_certificates() ANDs name/tin filters — a single search box needs
    # OR semantics (match name *or* TIN), so fetch by period/status only and
    # apply the combined text match here.
    result = search_certificates(
        session, period_from=period_start, period_to=period_end, status=status_filter, page=1, page_size=1000
    )
    if search.strip():
        needle = search.strip().lower()
        needle_digits = _digits_only(search)
        certs = [
            c
            for c in result.certificates
            if needle in c.payee.registered_name.lower() or needle_digits in _digits_only(c.payee.tin)
        ]
    else:
        certs = result.certificates

    if not certs:
        st.info("No certificates match your current filters.")
        return

    rows = []
    for c in certs:
        rows.append(
            {
                "Payee": c.payee.registered_name,
                "TIN": mask_tin(c.payee.tin),
                "Quarter": f"{c.period_start:%Y-%m} → {c.period_end:%Y-%m}",
                "Amount Paid": _amount_paid(c),
                "EWT": float(c.total_tax_withheld),
                "Status": _STATUS_LABEL[c.status.value],
                "Updated": c.updated_at.strftime("%Y-%m-%d %H:%M") if c.updated_at else "",
            }
        )
    df = pd.DataFrame(rows)

    st.caption(f"{len(certs)} certificate(s)")
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        key="cert_table",
        column_config={
            "Amount Paid": st.column_config.NumberColumn(format="₱%.2f"),
            "EWT": st.column_config.NumberColumn(format="₱%.2f"),
        },
    )
    selected_rows = event.selection["rows"] if event and event.selection else []
    selected_certs = [certs[i] for i in selected_rows]

    if selected_certs:
        st.markdown(
            f'<span style="background:{t["accent_bg"]};'
            f'color:{t["accent"]};padding:4px 10px;border-radius:6px;font-size:0.85rem;font-weight:600;">'
            f"{len(selected_certs)} selected</span>",
            unsafe_allow_html=True,
        )
        b_gen, b1, b2, b3, b4 = st.columns([1.6, 1.4, 1.4, 1.4, 4])
        with b_gen:
            if st.button("Generate PDF(s)", key="bulk_generate", use_container_width=True):
                from app.config import settings

                generated, failed = 0, 0
                for c in selected_certs:
                    try:
                        generate_certificate_pdf(session, c, settings.generated_pdfs_dir)
                        if c.status == CertificateStatus.DRAFT:
                            transition_status(session, c, CertificateStatus.GENERATED, current_user, "PDF generated.")
                        log_event(
                            session,
                            category=EventCategory.PDF_GENERATION,
                            severity=EventSeverity.INFO,
                            message=f"Generated unsigned PDF for certificate #{c.id}.",
                            certificate_id=c.id,
                        )
                        generated += 1
                    except Exception as exc:
                        log_event(
                            session,
                            category=EventCategory.PDF_GENERATION,
                            severity=EventSeverity.ERROR,
                            message=f"Failed to generate PDF for certificate #{c.id}.",
                            technical_detail=repr(exc),
                            certificate_id=c.id,
                        )
                        failed += 1
                session.commit()
                if failed:
                    st.warning(f"Generated {generated} PDF(s), {failed} failed — check the Audit Log for details.")
                else:
                    st.success(f"Generated {generated} PDF(s).")
                st.rerun()
        with b1:
            if st.button("Mark Forwarded", key="bulk_forward", use_container_width=True):
                changed = bulk_transition_status(
                    session, selected_certs, CertificateStatus.FORWARDED, current_user, "Bulk action."
                )
                session.commit()
                st.success(f"{changed} certificate(s) marked forwarded.")
                st.rerun()
        with b2:
            if st.button("Void", key="bulk_void", use_container_width=True):
                changed = bulk_transition_status(
                    session, selected_certs, CertificateStatus.VOID, current_user, "Bulk action."
                )
                session.commit()
                st.success(f"{changed} certificate(s) voided.")
                st.rerun()
        with b3:
            unsigned_paths = [(c, c.pdf_unsigned_path) for c in selected_certs if c.pdf_unsigned_path]
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for c, path in unsigned_paths:
                    try:
                        zf.write(path, arcname=f"certificate_{c.id}.pdf")
                    except OSError:
                        continue
            st.download_button(
                "Download",
                zip_buffer.getvalue(),
                file_name="certificates.zip",
                mime="application/zip",
                key="bulk_download",
                use_container_width=True,
                disabled=not unsigned_paths,
            )
        if len(selected_certs) == 1:
            with b4:
                if st.button("Open Certificate →", key="open_drawer", type="primary"):
                    st.session_state["selected_certificate_id"] = selected_certs[0].id
                    _certificate_drawer(session, selected_certs[0].id, current_user)
