"""The one reusable list-row primitive, used identically by every
middle-panel list (Certificates, Uploads, Search results, Logs)."""

from __future__ import annotations

import streamlit as st


def status_badge(label: str, variant: str = "neutral") -> None:
    """variant: one of neutral | accent | success | warning | error."""
    st.markdown(
        f'<span class="status-badge status-badge--{variant}">{label}</span>',
        unsafe_allow_html=True,
    )


def render_selectable_card(
    title: str,
    subtitle: str,
    badge: tuple[str, str] | None,
    is_selected: bool,
    key: str,
    button_label: str = "View details",
) -> bool:
    """Renders one bordered card; returns True the run its button is clicked.

    The selected card gets the fixed container key "card_selected" so
    styles.py can highlight it — safe because at most one card in a given
    list is selected at a time, so the key stays unique app-wide.
    """
    container_key = "card_selected" if is_selected else f"card_{key}"
    with st.container(border=True, key=container_key):
        st.markdown(f"**{title}**")
        if subtitle:
            st.caption(subtitle)
        if badge is not None:
            status_badge(*badge)
        return st.button(
            "Selected" if is_selected else button_label,
            key=f"select_{key}",
            use_container_width=True,
            disabled=is_selected,
            type="primary" if is_selected else "secondary",
        )
