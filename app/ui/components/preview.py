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


def _field(label: str, value: str, t: dict) -> str:
    return (
        f'<div style="margin-bottom:14px;">'
        f'<p style="font-size:0.72rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;'
        f'color:{t["text_muted"]};margin:0 0 4px 0;">{label}</p>'
        f'<p style="font-size:0.95rem;font-weight:700;color:{t["text_primary"]};margin:0;">{value}</p>'
        f"</div>"
    )


def render_certificate_metrics(certificate) -> None:
    """The metadata grid: Amount Paid / Tax Base / EWT / period / TIN /
    address — the certificate-level facts the Summary drawer tab shows
    above the PDF preview. Rendered as one bordered card of uniform
    uppercase-label/bold-value fields (matching the redesign reference's
    field-grid, see app/ui/styles.py's module docstring) instead of mixed
    st.metric widgets + inline text, which read as disjointed."""
    payee = certificate.payee
    amount_paid = certificate.total_gross - certificate.total_tax_withheld
    t = page_tokens(st.session_state.get("theme", "light"))

    with st.container(border=True):
        st.markdown(
            f'<p style="font-size:0.85rem;font-weight:700;color:{t["text_primary"]};margin:0 0 12px 0;">'
            f"Certificate Details</p>",
            unsafe_allow_html=True,
        )
        row1 = st.columns(2)
        row1[0].markdown(_field("Amount Paid", f"₱{amount_paid:,.2f}", t), unsafe_allow_html=True)
        row1[1].markdown(_field("Tax Base", f"₱{certificate.total_gross:,.2f}", t), unsafe_allow_html=True)
        row2 = st.columns(2)
        row2[0].markdown(_field("EWT Withheld", f"₱{certificate.total_tax_withheld:,.2f}", t), unsafe_allow_html=True)
        row2[1].markdown(
            _field(
                "Date Generated",
                f"{certificate.generated_at:%Y-%m-%d}" if certificate.generated_at else "—",
                t,
            ),
            unsafe_allow_html=True,
        )
        row3 = st.columns(2)
        row3[0].markdown(
            _field("Period", f"{certificate.period_start:%Y-%m-%d} to {certificate.period_end:%Y-%m-%d}", t),
            unsafe_allow_html=True,
        )
        row3[1].markdown(_field("TIN", f"{payee.tin} ({mask_tin(payee.tin)})", t), unsafe_allow_html=True)
        st.markdown(_field("Payee", payee.registered_name, t), unsafe_allow_html=True)
        st.markdown(_field("Address", payee.address or "—", t), unsafe_allow_html=True)
