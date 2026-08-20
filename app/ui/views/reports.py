"""Reports: quarterly summary (real), plus Filing Packet / Data Export —
both placeholders. Export has no backend today (confirmed absent from
app/core/ during the gap audit; the design spec itself calls this out as
currently missing), so these render as disabled affordances with an
explicit note rather than fake buttons that silently do nothing.
"""

from __future__ import annotations

import streamlit as st

from app.core.dashboard import quarterly_summary
from app.ui.layout import render_quarter_picker, render_top_bar
from app.ui.state import current_quarter_bounds, current_quarter_label
from app.ui.styles import page_tokens, status_colors

_STATUS_BAR_ORDER = [
    ("completed_signed", "Signed", "success"),
    ("forwarded", "Forwarded", "violet"),
    ("generated", "Generated", "accent"),
    ("draft", "Draft", "neutral"),
]


def _peso(amount) -> str:
    return f"₱{amount:,.2f}"


def render_reports_view(session, current_user: str) -> None:
    render_top_bar(session)
    t = page_tokens(st.session_state["theme"])
    colors = status_colors(st.session_state["theme"])

    header_col, quarter_col = st.columns([4, 1.3])
    with header_col:
        st.markdown("### Reports")
    with quarter_col:
        render_quarter_picker()
    st.caption("Quarterly summaries, filing packets, and data exports.")

    period_start, period_end = current_quarter_bounds()
    quarter_label = current_quarter_label()
    summary = quarterly_summary(session, period_start, period_end)

    with st.container(border=True):
        st.markdown(f"**Quarterly Summary — {quarter_label}**")
        stat_cols = st.columns(4)
        stats = [
            ("Certificates", str(summary.certificate_count)),
            ("Payees", str(summary.payee_count)),
            ("Total Amount Paid", _peso(summary.total_amount_paid)),
            ("Total EWT", _peso(summary.total_ewt)),
        ]
        for col, (label, value) in zip(stat_cols, stats):
            with col:
                st.markdown(
                    f'<p class="tabular" style="font-size:1.1rem;font-weight:700;color:{t["text_primary"]};margin:0;">{value}</p>'
                    f'<p style="font-size:0.75rem;color:{t["text_muted"]};margin:0;">{label}</p>',
                    unsafe_allow_html=True,
                )

        st.write("")
        st.markdown(
            f'<p style="font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
            f'text-transform:uppercase;color:{t["text_muted"]};margin-bottom:6px;">Status Distribution</p>',
            unsafe_allow_html=True,
        )
        total = max(summary.certificate_count, 1)
        for status_value, label, variant in _STATUS_BAR_ORDER:
            count = summary.status_counts.get(status_value, 0)
            pct = int(count / total * 100)
            _, fg, _ = colors[variant]
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
                f'<span style="width:80px;font-size:0.78rem;color:{t["text_secondary"]};">{label}</span>'
                f'<div style="flex:1;height:8px;background:{t["border_subtle"]};border-radius:999px;overflow:hidden;">'
                f'<div style="width:{pct}%;height:100%;background:{fg};border-radius:999px;"></div></div>'
                f'<span class="tabular" style="width:32px;text-align:right;font-size:0.78rem;color:{t["text_muted"]};">{count}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.write("")
    col_packet, col_export = st.columns(2, gap="medium")

    with col_packet:
        with st.container(border=True):
            st.markdown("**Filing Packet**")
            st.caption("Generate a complete filing packet for submission.")
            st.button(
                "Download PDF Packet",
                disabled=True,
                use_container_width=True,
                key="packet_pdf",
                help="Not yet available — see the front-end redesign gap list (P1).",
            )
            st.button(
                "Export Excel",
                disabled=True,
                use_container_width=True,
                key="packet_excel",
                help="Not yet available — see the front-end redesign gap list (P1).",
            )
            st.caption("⚠️ Not yet implemented — no export/packaging logic exists in the backend yet.")

    with col_export:
        with st.container(border=True):
            st.markdown("**Data Export**")
            st.caption("Export raw certificate and transaction data.")
            for label in ["Certificates — CSV", "Certificates — Excel", "Transactions — CSV", "Payees — CSV"]:
                row_label, row_btn = st.columns([3, 1])
                row_label.caption(label)
                row_btn.button(
                    "Export",
                    disabled=True,
                    key=f"export_{label}",
                    help="Not yet available — see the front-end redesign gap list (P1).",
                )
            st.caption("⚠️ Not yet implemented — no export/packaging logic exists in the backend yet.")
