"""One CSS injection for the whole workspace's visual language.

Scoped to `st.container(key=...)` hooks (Streamlit >=1.37 emits an
`st-key-<key>` class on that container's DOM node) and stable Streamlit
test-ids — never blanket tag selectors — so this can't bleed into
Streamlit's own chrome or fight a future Streamlit release's markup.

Palette matches the dark-mode design reference under
Files/DarkDesign/DarkModeDesignSystem-main (a Figma Make mockup of this
exact app's Payees/Uploads/Logs screens). Streamlit's own dark theme
(.streamlit/config.toml) handles native widget chrome; this file only
covers the custom pieces: badges, selectable cards, list scrollbars, and
the tab underline.
"""

from __future__ import annotations

import streamlit as st

# Surfaces
BG_BASE = "#111827"
BG_SURFACE = "#1F2937"
BG_ELEVATED = "#374151"
BG_INPUT = "#0F172A"

# Borders
BORDER = "#374151"
BORDER_HOVER = "#3B5998"

# Text
TEXT_PRIMARY = "#F3F4F6"
TEXT_SECONDARY = "#9CA3AF"
TEXT_MUTED = "#6B7280"

# Accent
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}}
code, pre, div[data-testid="stCodeBlock"] {{
    font-family: 'JetBrains Mono', monospace !important;
}}

/* Buttons */
div[data-testid="stButton"] button[kind="primary"] {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
div[data-testid="stButton"] button[kind="primary"]:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
div[data-testid="stButton"] button[kind="secondary"] {{
    background-color: {BG_SURFACE};
    border-color: {BORDER};
    color: {TEXT_SECONDARY};
}}
div[data-testid="stButton"] button[kind="secondary"]:hover {{
    background-color: {BG_ELEVATED};
    border-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
}}

/* Bordered containers (cards, panels) */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 10px !important;
    border-color: {BORDER} !important;
    background-color: {BG_SURFACE};
}}

/* Selectable list-row cards: hover + selected states */
div[class*="st-key-card_"] > div[data-testid="stVerticalBlockBorderWrapper"] {{
    transition: background-color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}}
div[class*="st-key-card_"]:hover > div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-color: {BORDER_HOVER} !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}}
div.st-key-card_selected_payees div[data-testid="stVerticalBlockBorderWrapper"],
div.st-key-card_selected_uploads div[data-testid="stVerticalBlockBorderWrapper"],
div.st-key-card_selected_logs div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-color: {ACCENT} !important;
    border-width: 2px !important;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.25);
}}

/* Status/severity badge pills — translucent fill + matching border, per
   the reference Badge component's blue/amber/green/red/gray variants. */
.status-badge {{
    display: inline-flex;
    align-items: center;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    border: 1px solid transparent;
}}
.status-badge--neutral {{
    background: {BG_ELEVATED};
    color: {TEXT_SECONDARY};
    border-color: rgba(75, 85, 99, 0.5);
}}
.status-badge--accent {{
    background: rgba(30, 58, 138, 0.5);
    color: #93C5FD;
    border-color: rgba(59, 130, 246, 0.4);
}}
.status-badge--success {{
    background: rgba(2, 44, 34, 0.7);
    color: #6EE7B7;
    border-color: rgba(4, 120, 87, 0.5);
}}
.status-badge--warning {{
    background: rgba(69, 26, 3, 0.7);
    color: #FCD34D;
    border-color: rgba(180, 83, 9, 0.5);
}}
.status-badge--error {{
    background: rgba(69, 10, 10, 0.7);
    color: #FCA5A5;
    border-color: rgba(185, 28, 28, 0.5);
}}

/* Scrollable list containers keep their own scrollbar, not the page's.
   One rule per tab's list container — element keys must be unique across
   the whole app now that st.tabs() renders every tab's body each rerun
   (unlike the old if/elif dispatch, which only ever rendered one). */
div.st-key-payees_list,
div.st-key-uploads_list,
div.st-key-logs_list {{
    padding-right: 4px;
}}
div.st-key-payees_list *::-webkit-scrollbar,
div.st-key-uploads_list *::-webkit-scrollbar,
div.st-key-logs_list *::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
}}
div.st-key-payees_list *::-webkit-scrollbar-thumb,
div.st-key-uploads_list *::-webkit-scrollbar-thumb,
div.st-key-logs_list *::-webkit-scrollbar-thumb {{
    background: {BORDER};
    border-radius: 3px;
}}

/* Top tab bar underline, matching the reference nav */
div[data-testid="stTabs"] button[data-baseweb="tab"] {{
    font-weight: 600;
}}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
    background-color: {ACCENT} !important;
}}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
