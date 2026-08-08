"""The single shared document-preview implementation.

`render_document_preview` is called identically from both the Certificates
tab and the Search tab (search results ARE certificates) — this is the one
place PDF bytes ever get read and embedded; no tab re-implements it.

PDF preview approach: base64-encode the already-generated PDF and embed it
via a data-URI <iframe>. Zero new dependencies, keeps generation (see
app/core/pdf_generator.py) and preview cleanly separate. Tradeoff: inline
rendering depends on the viewer's own PDF support (reliable on desktop
Chrome/Edge/Firefox; some locked-down browsers disable it) — every preview
is paired with a working Download button as a fallback that always works.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from app.core.security import mask_tin
from app.ui.components.cards import status_badge
from app.ui.styles import BORDER

STATUS_BADGE_VARIANT = {
    "draft": "neutral",
    "generated": "accent",
    "forwarded": "accent",
    "completed_signed": "success",
    "void": "error",
}


def render_pdf_preview(pdf_path: str | Path | None, label: str, key_suffix: str) -> None:
    st.markdown(f"**{label}**")
    if not pdf_path:
        st.info("Not generated yet.")
        return
    path = Path(pdf_path)
    try:
        data = path.read_bytes()
    except OSError:
        st.info("Preview unavailable — file missing on disk. Use Download once regenerated.")
        return

    b64 = base64.b64encode(data).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0" '
        f'width="100%" height="700" '
        f'style="border:1px solid {BORDER}; border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
    )
    st.download_button(
        f"Download {label.lower()}",
        data,
        file_name=path.name,
        mime="application/pdf",
        key=f"dl_{key_suffix}",
    )


def render_document_preview(certificate) -> None:
    payee = certificate.payee
    st.subheader(f"Certificate #{certificate.id}")
    st.write(f"**{payee.registered_name}** — {mask_tin(payee.tin)}")
    st.caption(f"{certificate.period_start:%Y-%m-%d} to {certificate.period_end:%Y-%m-%d}")
    status_badge(
        certificate.status.value, STATUS_BADGE_VARIANT.get(certificate.status.value, "neutral")
    )

    c1, c2 = st.columns(2)
    c1.metric("Total gross", f"₱{certificate.total_gross:,.2f}")
    c2.metric("Total tax withheld", f"₱{certificate.total_tax_withheld:,.2f}")
    st.write(f"**Full TIN:** {payee.tin}")
    st.write(f"**Address:** {payee.address or '—'}")

    st.divider()
    render_pdf_preview(
        certificate.pdf_unsigned_path, "Unsigned PDF", key_suffix=f"unsigned_{certificate.id}"
    )
    if certificate.pdf_signed_path:
        st.divider()
        render_pdf_preview(
            certificate.pdf_signed_path, "Signed copy", key_suffix=f"signed_{certificate.id}"
        )
