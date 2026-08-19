"""Overview: the operational dashboard. Answers "what needs my attention
right now" for the globally-selected quarter — not vanity metrics.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.core.dashboard import attention_items, quarter_kpis, quarterly_summary, recent_activity, workflow_stage_counts
from app.core.models import CertificateStatus, Payor
from app.ui.layout import render_top_bar
from app.ui.state import current_quarter_bounds, current_quarter_label
from app.ui.styles import page_tokens, status_colors

_KPI_VARIANT = {
    "generated": "accent",
    "for_review": "warning",
    "forwarded": "violet",
    "completed": "success",
    "exceptions": "error",
}
_KPI_LABEL = {
    "generated": "Generated",
    "for_review": "For Review",
    "forwarded": "Forwarded",
    "completed": "Completed",
    "exceptions": "Exceptions",
}
_KPI_SUB = {
    "generated": "This quarter",
    "for_review": "Unresolved warnings/errors",
    "forwarded": "Sent to payees",
    "completed": "Signed copies received",
    "exceptions": "Errors or line-item overflow",
}
_SEVERITY_ICON = {"warning": "⚠️", "info": "ℹ️", "error": "🛑"}


def _peso(amount) -> str:
    return f"₱{amount:,.2f}"


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def render_overview_view(session, current_user: str) -> None:
    render_top_bar(session)

    t = page_tokens(st.session_state["theme"])
    colors = status_colors(st.session_state["theme"])
    period_start, period_end = current_quarter_bounds()
    quarter_label = current_quarter_label()

    st.markdown(f"### {_greeting()}, {current_user.replace('_', ' ').title()}.")
    st.caption(f"Here's what needs your attention this {quarter_label}.")

    kpis = quarter_kpis(session, period_start, period_end)
    kpi_values = {
        "generated": kpis.generated,
        "for_review": kpis.for_review,
        "forwarded": kpis.forwarded,
        "completed": kpis.completed,
        "exceptions": kpis.exceptions,
    }
    kpi_cols = st.columns(5, gap="small")
    for col, key in zip(kpi_cols, kpi_values):
        variant = _KPI_VARIANT[key]
        bg, fg, border = colors[variant]
        with col:
            st.markdown(
                f'<div class="kpi-card" style="background:{bg};border-color:{border};">'
                f'<div class="kpi-value" style="color:{fg};">{kpi_values[key]}</div>'
                f'<div class="kpi-label" style="color:{t["text_secondary"]};">{_KPI_LABEL[key]}</div>'
                f'<div class="kpi-sub" style="color:{t["text_faint"]};">{_KPI_SUB[key]}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button("View →", key=f"kpi_{key}", use_container_width=True):
                st.session_state["view"] = "certificates"
                st.rerun()

    st.write("")

    # --- Workflow progress -------------------------------------------------
    with st.container(border=True):
        st.markdown(
            f'<p style="font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
            f'text-transform:uppercase;color:{t["text_faint"]};margin-bottom:6px;">'
            f"{quarter_label} Workflow Progress</p>",
            unsafe_allow_html=True,
        )
        stage_counts = workflow_stage_counts(session, period_start, period_end)
        stages = [s for s in stage_counts.as_stages() if s[0] != CertificateStatus.VOID.value]
        stage_cols = st.columns(len(stages), gap="small")
        for col, (status_value, label, count) in zip(stage_cols, stages):
            with col:
                num_bg = t["accent"] if count > 0 else t["border"]
                num_fg = "#FFFFFF" if count > 0 else t["text_faint"]
                st.markdown(
                    f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;">'
                    f'<div class="workflow-stage-num" style="background:{num_bg};color:{num_fg};">{count}</div>'
                    f'<span style="font-size:0.72rem;color:{t["text_muted"]};">{label}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if st.button("View", key=f"stage_{status_value}", use_container_width=True):
                    st.session_state["certificates_filters"]["status"] = status_value
                    st.session_state["view"] = "certificates"
                    st.rerun()

    st.write("")

    attn_col, activity_col = st.columns(2, gap="medium")
    payor = session.query(Payor).first()
    payor_is_placeholder = payor is not None and payor.tin == "000-000-000-000"

    with attn_col:
        with st.container(border=True):
            items = attention_items(session, period_start, period_end, payor_is_placeholder=payor_is_placeholder)
            st.markdown(f"**Needs Your Attention** &nbsp;·&nbsp; {len(items)} item(s)")
            if not items:
                st.caption("Nothing needs attention right now.")
            for item in items:
                bg, fg, border = colors[item.severity if item.severity != "error" else "error"]
                icon = _SEVERITY_ICON.get(item.severity, "ℹ️")
                col_text, col_cta = st.columns([4, 1.2])
                with col_text:
                    st.markdown(
                        f'<div class="attention-card" style="background:{bg};border-color:{border};">'
                        f'<span>{icon}</span><div>'
                        f'<div class="attention-title" style="color:{fg};">{item.title}</div>'
                        f'<div class="attention-desc" style="color:{t["text_secondary"]};">{item.description}</div>'
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )
                with col_cta:
                    if st.button(item.cta_label, key=f"attn_{item.title[:20]}", use_container_width=True):
                        if item.target_view == "settings":
                            st.session_state["view"] = "more"
                            st.session_state["more_section"] = "settings"
                        else:
                            st.session_state["view"] = item.target_view
                        st.rerun()

    with activity_col:
        with st.container(border=True):
            top, link = st.columns([3, 1.2])
            top.markdown("**Recent Activity**")
            if link.button("View audit log", key="activity_view_log", use_container_width=True):
                st.session_state["view"] = "more"
                st.session_state["more_section"] = "audit"
                st.rerun()
            activity = recent_activity(session, limit=8)
            if not activity:
                st.caption("No activity recorded yet.")
            for entry in activity:
                st.markdown(
                    f'<div style="padding:6px 0;border-bottom:1px solid {t["border_subtle"]};">'
                    f'<span style="font-size:0.85rem;color:{t["text_secondary"]};">{entry.message}</span><br/>'
                    f'<span style="font-size:0.72rem;color:{t["text_faint"]};">'
                    f'{entry.category} · {entry.timestamp:%Y-%m-%d %H:%M}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.write("")

    # --- Quarter summary -----------------------------------------------------
    with st.container(border=True):
        st.markdown(
            f'<p style="font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
            f'text-transform:uppercase;color:{t["text_faint"]};margin-bottom:6px;">'
            f"{quarter_label} Summary</p>",
            unsafe_allow_html=True,
        )
        summary = quarterly_summary(session, period_start, period_end)
        sum_cols = st.columns(4, gap="medium")
        stats = [
            ("Total Certificates", str(summary.certificate_count), "this quarter"),
            ("Total Payees", str(summary.payee_count), "unique payees"),
            ("Total Amount Paid", _peso(summary.total_amount_paid), "across all certs"),
            ("Total EWT", _peso(summary.total_ewt), "withheld"),
        ]
        for col, (label, value, sub) in zip(sum_cols, stats):
            with col:
                st.markdown(
                    f'<p class="tabular" style="font-size:1.15rem;font-weight:700;color:{t["text_primary"]};margin:0;">{value}</p>'
                    f'<p style="font-size:0.78rem;font-weight:600;color:{t["text_secondary"]};margin:0;">{label}</p>'
                    f'<p style="font-size:0.72rem;color:{t["text_faint"]};margin:0;">{sub}</p>',
                    unsafe_allow_html=True,
                )
