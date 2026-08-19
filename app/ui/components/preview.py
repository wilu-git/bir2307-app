"""The single shared document-preview implementation.

`render_pdf_preview` is the one place PDF bytes ever get read and embedded
— every certificate/payee view that needs to show a generated PDF reuses
this instead of re-implementing it.

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
from app.ui.styles import page_tokens


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

    border = page_tokens(st.session_state.get("theme", "light"))["border"]
    b64 = base64.b64encode(data).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0" '
        f'width="100%" height="700" '
        f'style="border:1px solid {border}; border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
    )
    st.download_button(
        f"Download {label.lower()}",
        data,
        file_name=path.name,
        mime="application/pdf",
        key=f"dl_{key_suffix}",
    )


def render_certificate_metrics(certificate) -> None:
    """The metadata grid: Amount Paid / Tax Base / EWT / period / TIN /
    address — the certificate-level facts the Summary drawer tab shows
    above the PDF preview."""
    payee = certificate.payee
    amount_paid = certificate.total_gross - certificate.total_tax_withheld
    c1, c2 = st.columns(2)
    c1.metric("Amount paid", f"₱{amount_paid:,.2f}")
    c2.metric("EWT withheld", f"₱{certificate.total_tax_withheld:,.2f}")
    c3, c4 = st.columns(2)
    c3.metric("Total gross", f"₱{certificate.total_gross:,.2f}")
    c4.metric(
        "Date generated",
        f"{certificate.generated_at:%Y-%m-%d}" if certificate.generated_at else "—",
    )
    st.caption(f"Period: {certificate.period_start:%Y-%m-%d} to {certificate.period_end:%Y-%m-%d}")
    st.write(f"**{payee.registered_name}**")
    st.write(f"**Full TIN:** {payee.tin} &nbsp;·&nbsp; **Masked:** {mask_tin(payee.tin)}", unsafe_allow_html=False)
    st.write(f"**Address:** {payee.address or '—'}")
