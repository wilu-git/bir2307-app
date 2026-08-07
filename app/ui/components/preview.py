"""The single shared document-preview implementation.

`render_document_preview` is called identically from both the Certificates
tab and the Search tab (search results ARE certificates) — this is the one
place PDF bytes ever get read and embedded; no tab re-implements it.

PDF preview approach: publish the already-generated PDF into app/static/
(Streamlit's supported static-file directory, served same-origin once
`server.enableStaticServing = true` — see .streamlit/config.toml) and embed
it via a plain <iframe src="app/static/...">. Keeps generation (see
app/core/pdf_generator.py) and preview cleanly separate, zero new
dependencies. An earlier version embedded the PDF as a base64 data: URI
instead — simpler, but privacy-hardened browsers (Brave Shields, some
locked-down corporate configs) block data: URIs inside <iframe>s outright,
which a same-origin static-file URL doesn't trigger. Every preview is still
paired with a working Download button as a fallback that always works.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.core.security import mask_tin
from app.ui.components.cards import status_badge
from app.ui.styles import BORDER

# Streamlit only serves static files from <main_script_dir>/static/, i.e.
# sibling to app/main.py — this resolves to that exact directory regardless
# of where this module itself lives.
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def _publish_to_static(path: Path) -> str:
    """Copies `path` into app/static/ (once per content version) and
    returns the same-origin URL Streamlit serves it at.

    Filenames are content-versioned by source mtime so a regenerated PDF
    gets a fresh URL instead of colliding with a browser-cached old copy.
    Copies accumulate in app/static/ over time rather than being pruned —
    an acceptable tradeoff given this app's certificate volume (one PDF
    per payee per quarter; dozens, not thousands).
    """
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    versioned_name = f"{path.stem}_{int(path.stat().st_mtime)}{path.suffix}"
    dest = _STATIC_DIR / versioned_name
    if not dest.exists():
        dest.write_bytes(path.read_bytes())
    return f"app/static/{versioned_name}"


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
        url = _publish_to_static(path)
        data = path.read_bytes()
    except OSError:
        st.info("Preview unavailable — file missing on disk. Use Download once regenerated.")
        return

    st.markdown(
        f'<iframe src="{url}#toolbar=0" '
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
