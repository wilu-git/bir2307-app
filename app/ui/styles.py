"""One CSS injection for the whole workspace's visual language.

Scoped to `st.container(key=...)` hooks (Streamlit >=1.37 emits an
`st-key-<key>` class on that container's DOM node) and stable Streamlit
test-ids — never blanket tag selectors — so this can't bleed into
Streamlit's own chrome or fight a future Streamlit release's markup.

There is no existing theming anywhere in this project (no
.streamlit/config.toml, no CSS assets) to match, so this introduces the
palette from scratch: one accent color, white/neutral background, subtle
borders, rounded cards, restrained shadows.
"""

from __future__ import annotations

import streamlit as st

ACCENT = "#2563EB"
BORDER = "#E5E7EB"
TEXT_MUTED = "#6B7280"

_CSS = f"""
<style>
div[data-testid="stButton"] button[kind="primary"] {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
div[data-testid="stButton"] button[kind="primary"]:hover {{
    background-color: #1D4ED8;
    border-color: #1D4ED8;
}}

/* Selectable cards in the middle panel */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 10px !important;
    border-color: {BORDER} !important;
}}
div.st-key-card_selected_payees div[data-testid="stVerticalBlockBorderWrapper"],
div.st-key-card_selected_uploads div[data-testid="stVerticalBlockBorderWrapper"],
div.st-key-card_selected_logs div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-color: {ACCENT} !important;
    border-width: 2px !important;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.15);
}}

/* Status/severity badge pills */
.status-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}}
.status-badge--neutral {{ background: #F3F4F6; color: {TEXT_MUTED}; }}
.status-badge--accent  {{ background: #DBEAFE; color: {ACCENT}; }}
.status-badge--success {{ background: #D1FAE5; color: #047857; }}
.status-badge--warning {{ background: #FEF3C7; color: #B45309; }}
.status-badge--error   {{ background: #FEE2E2; color: #B91C1C; }}

/* Scrollable list containers keep their own scrollbar, not the page's.
   One rule per tab's list container — element keys must be unique across
   the whole app now that st.tabs() renders every tab's body each rerun
   (unlike the old if/elif dispatch, which only ever rendered one). */
div.st-key-payees_list,
div.st-key-uploads_list,
div.st-key-logs_list {{
    padding-right: 4px;
}}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
