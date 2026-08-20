"""One CSS injection for the whole workspace's visual language.

Palette and component vocabulary follow the redesign reference under
Files/BIR2307_Figma (a Figma Make mockup: sidebar shell, KPI cards, status
badges, drawers-as-dialogs, data tables). That reference is a single light
theme; dark mode is this app's own addition (user chose "offer both" over
"light only" or "dark only" — see PROJECT memory).

Streamlit's native widget chrome (inputs, buttons, selects, dataframe) is
only themeable per-server via .streamlit/config.toml, which is fixed at
process start — there is no supported way to swap it per browser session.
config.toml is set to the light palette below as the base; toggling to
dark re-colors the page via aggressive `!important` CSS overrides on
Streamlit's stable `data-testid`/`aria-*` selectors instead. This works for
everything tested (buttons, inputs, selects, checkboxes, dataframe,
expanders, dialogs, alerts) but is inherently a CSS override, not a true
theme switch — flag it if some future Streamlit release renders a widget
this doesn't reach.

Scoped to `st.container(key=...)` hooks (Streamlit >=1.37 emits an
`st-key-<key>` class on that container's DOM node) and stable Streamlit
test-ids — never blanket tag selectors — so this can't bleed into
Streamlit's own chrome or fight a future Streamlit release's markup.

Contrast: `text_faint` used to be the color for captions, field labels,
KPI sub-text, timestamps, etc. — real, meaningful text — but at 2.4-2.6:1
(light) / 3.7-3.9:1 (dark) it fails WCAG AA's 4.5:1 minimum for normal
text, which is what "hard to read" reports traced back to. `text_faint` is
now decorative-only (borders, placeholder ghost text) and every call site
that renders actual text uses `text_muted` instead, which was retuned to
clear 4.5:1 on both themes' surface/bg colors.
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

LIGHT = {
    "bg": "#F8FAFC",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "border": "#E2E8F0",
    "border_subtle": "#F1F5F9",
    "text_primary": "#0F172A",
    "text_secondary": "#334155",
    "text_muted": "#5B6B80",
    "text_faint": "#8494A8",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_bg": "#EFF6FF",
    "accent_bg_strong": "#DBEAFE",
    "input_bg": "#F8FAFC",
    "shadow": "rgba(15, 23, 42, 0.08)",
    "overlay": "rgba(15, 23, 42, 0.4)",
}

DARK = {
    "bg": "#0B1220",
    "surface": "#111827",
    "surface_alt": "#1A2436",
    "border": "#334155",
    "border_subtle": "#1E293B",
    "text_primary": "#F1F5F9",
    "text_secondary": "#CBD5E1",
    "text_muted": "#94A3B8",
    "text_faint": "#72839A",
    "accent": "#3B82F6",
    "accent_hover": "#60A5FA",
    "accent_bg": "rgba(37, 99, 235, 0.16)",
    "accent_bg_strong": "rgba(37, 99, 235, 0.28)",
    "input_bg": "#0F172A",
    "shadow": "rgba(0, 0, 0, 0.5)",
    "overlay": "rgba(0, 0, 0, 0.6)",
}

# The sidebar is dark in both app themes — matches the source design, where
# `bg-sidebar` (#0F172A) never changes regardless of the main content theme.
SIDEBAR = {
    "bg": "#0F172A",
    "hover": "#1E293B",
    "active": "#1D4ED8",
    "text": "#94A3B8",
    "text_active": "#FFFFFF",
    "border": "#1E293B",
}

# Certificate-status badge variants, light/dark. "void" additionally gets a
# strikethrough via the --void modifier class.
STATUS_LIGHT = {
    "neutral": ("#F1F5F9", "#475569", "#E2E8F0"),
    "accent": ("#EFF6FF", "#1D4ED8", "#DBEAFE"),
    "violet": ("#F5F3FF", "#6D28D9", "#EDE9FE"),
    "success": ("#ECFDF5", "#047857", "#D1FAE5"),
    "warning": ("#FFFBEB", "#B45309", "#FEF3C7"),
    "error": ("#FEF2F2", "#B91C1C", "#FEE2E2"),
}
STATUS_DARK = {
    "neutral": ("#1F2937", "#94A3B8", "rgba(75, 85, 99, 0.5)"),
    "accent": ("rgba(30, 58, 138, 0.5)", "#93C5FD", "rgba(59, 130, 246, 0.4)"),
    "violet": ("rgba(76, 29, 149, 0.5)", "#C4B5FD", "rgba(124, 58, 237, 0.4)"),
    "success": ("rgba(2, 44, 34, 0.7)", "#6EE7B7", "rgba(4, 120, 87, 0.5)"),
    "warning": ("rgba(69, 26, 3, 0.7)", "#FCD34D", "rgba(180, 83, 9, 0.5)"),
    "error": ("rgba(69, 10, 10, 0.7)", "#FCA5A5", "rgba(185, 28, 28, 0.5)"),
}

# Certificate lifecycle -> badge variant (draft/generated/forwarded/
# completed_signed/void map to the model's CertificateStatus values).
CERT_STATUS_VARIANT = {
    "draft": "neutral",
    "generated": "accent",
    "forwarded": "violet",
    "completed_signed": "success",
    "void": "void",
}
# Event/log severity -> badge variant.
SEVERITY_VARIANT = {"info": "accent", "warning": "warning", "error": "error"}


def _badge_css(tokens: dict, is_dark: bool) -> str:
    rules = []
    for variant, (bg, fg, border) in tokens.items():
        rules.append(
            f".status-badge--{variant} {{ background: {bg}; color: {fg}; "
            f"border-color: {border}; }}"
        )
    void_bg, void_fg, void_border = tokens["neutral"]
    rules.append(
        f".status-badge--void {{ background: {void_bg}; color: {void_fg}; "
        f"border-color: {void_border}; text-decoration: line-through; opacity: 0.7; }}"
    )
    return "\n".join(rules)


def _theme_css(t: dict, is_dark: bool) -> str:
    """Everything that differs between light/dark: page + native-widget
    chrome. `t` is LIGHT or DARK."""
    badge_tokens = STATUS_DARK if is_dark else STATUS_LIGHT
    return f"""
/* Page background/text */
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {{
    background: {t["bg"]} !important;
    color: {t["text_primary"]} !important;
}}
[data-testid="stAppViewContainer"] * {{ color: inherit; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span {{ color: {t["text_secondary"]}; }}
h1, h2, h3, h4, h5, [data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3 {{
    color: {t["text_primary"]} !important;
}}
[data-testid="stCaptionContainer"], .stCaption {{ color: {t["text_muted"]} !important; }}

/* Bordered containers / cards */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    background: {t["surface"]};
    border-color: {t["border"]} !important;
    border-radius: 10px !important;
}}

/* Buttons — includes stPopoverButton (e.g. the Certificates "Filters"
   trigger), which is a sibling testid to stButton, not nested inside it,
   so the plain div[data-testid="stButton"] selector above never reached
   it and it rendered as an unstyled white box in dark mode. */
div[data-testid="stButton"] button[kind="primary"],
button[data-testid="stPopoverButton"][kind="primary"],
div[data-testid="stDownloadButton"] button {{
    background-color: {t["accent"]};
    border-color: {t["accent"]};
    color: #FFFFFF;
}}
div[data-testid="stButton"] button[kind="primary"]:hover,
button[data-testid="stPopoverButton"][kind="primary"]:hover,
div[data-testid="stDownloadButton"] button:hover {{
    background-color: {t["accent_hover"]};
    border-color: {t["accent_hover"]};
}}
div[data-testid="stButton"] button[kind="secondary"],
button[data-testid="stPopoverButton"][kind="secondary"] {{
    background-color: {t["surface"]};
    border-color: {t["border"]};
    color: {t["text_secondary"]};
}}
div[data-testid="stButton"] button[kind="secondary"]:hover,
button[data-testid="stPopoverButton"][kind="secondary"]:hover {{
    background-color: {t["surface_alt"]};
    border-color: {t["text_faint"]};
    color: {t["text_primary"]};
}}
div[data-testid="stButton"] button:disabled,
button[data-testid="stPopoverButton"]:disabled {{ opacity: 0.45; }}

/* Inputs / selects / checkboxes / date & number inputs */
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stDateInput"] input,
div[data-baseweb="select"] > div,
div[data-baseweb="input"] {{
    background-color: {t["input_bg"]} !important;
    border-color: {t["border"]} !important;
    color: {t["text_primary"]} !important;
}}
div[data-testid="stTextInput"] input::placeholder {{ color: {t["text_muted"]} !important; }}
[data-baseweb="popover"] [role="listbox"] {{
    background-color: {t["surface"]} !important;
    border-color: {t["border"]} !important;
}}
[data-baseweb="popover"] [role="option"] {{ color: {t["text_secondary"]} !important; }}
[data-baseweb="popover"] [role="option"]:hover {{ background-color: {t["surface_alt"]} !important; }}
label[data-testid="stWidgetLabel"] p {{ color: {t["text_muted"]} !important; }}

/* Checkboxes */
[data-testid="stCheckbox"] label span:first-child {{
    background-color: {t["input_bg"]} !important;
    border-color: {t["border"]} !important;
}}

/* File uploader */
[data-testid="stFileUploaderDropzone"] {{
    background-color: {t["surface_alt"]} !important;
    border-color: {t["border"]} !important;
}}
[data-testid="stFileUploaderDropzone"] * {{ color: {t["text_secondary"]} !important; }}

/* Expander */
[data-testid="stExpander"] {{
    background-color: {t["surface"]};
    border-color: {t["border"]} !important;
}}
[data-testid="stExpander"] summary {{ color: {t["text_primary"]} !important; }}

/* Popover content panel (e.g. Certificates' "Filters" dropdown) — like
   stPopoverButton above, this is a separate testid the blanket rules never
   reached, so it stayed hardcoded to the light background always. */
div[data-testid="stPopoverBody"] {{
    background-color: {t["surface"]} !important;
    border-color: {t["border"]} !important;
}}
div[data-testid="stPopoverBody"] * {{ color: {t["text_secondary"]}; }}

/* Dialog (used as our "drawer" / import wizard modal) */
div[role="dialog"] {{
    background-color: {t["surface"]} !important;
    border-color: {t["border"]};
}}
div[role="dialog"] * {{ color: {t["text_secondary"]}; }}
div[role="dialog"] h1, div[role="dialog"] h2, div[role="dialog"] h3 {{
    color: {t["text_primary"]} !important;
}}

/* Slide-out drawer backdrop: dimmed just enough to show a modal is open,
   without fully blacking out the rest of the interface behind it. */
div[data-testid="stDialog"] > div {{
    background: {t["overlay"]} !important;
}}

/* Tables (st.dataframe) */
div[data-testid="stDataFrame"] {{
    background-color: {t["surface"]};
    border-color: {t["border"]} !important;
}}
div[data-testid="stDataFrame"] [role="columnheader"] {{
    background-color: {t["surface_alt"]} !important;
    color: {t["text_muted"]} !important;
}}
div[data-testid="stDataFrame"] [role="gridcell"] {{ color: {t["text_secondary"]} !important; }}

/* Tabs (used inside drawers: Summary/Timeline/Signed Copy, Overview/Transactions/...) */
div[data-testid="stTabs"] button[data-baseweb="tab"] {{
    color: {t["text_muted"]} !important;
    font-weight: 500;
}}
div[data-testid="stTabs"] button[aria-selected="true"] {{ color: {t["accent"]} !important; }}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background-color: {t["accent"]} !important; }}
div[data-testid="stTabs"] [data-baseweb="tab-border"] {{ background-color: {t["border"]} !important; }}

/* Alerts (st.info/success/warning/error) restyled to flat tinted bars matching the badge palette */
div[data-testid="stAlertContainer"] {{ border-radius: 8px; border-width: 1px; border-style: solid; }}
div[data-testid="stAlertContainer"] p {{ color: inherit !important; }}

/* Sidebar (theme-independent dark — declared here too so it applies
   regardless of which theme block loads last) */
[data-testid="stSidebar"] {{
    background-color: {SIDEBAR["bg"]} !important;
    border-right: 1px solid {SIDEBAR["border"]};
}}
[data-testid="stSidebar"] * {{ color: {SIDEBAR["text"]}; }}

/* Status badges */
{_badge_css(badge_tokens, is_dark)}

/* Scrollbar */
*::-webkit-scrollbar {{ width: 6px; height: 6px; }}
*::-webkit-scrollbar-track {{ background: transparent; }}
*::-webkit-scrollbar-thumb {{ background: {t["border"]}; border-radius: 3px; }}
* {{ scrollbar-color: {t["border"]} transparent; }}
"""


_STATIC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }
h1, h2, h3, [data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; }
.tabular, code, pre, div[data-testid="stCodeBlock"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-variant-numeric: tabular-nums;
}

/* Status/severity badge pills — shared shape, color comes from the
   per-theme block above. */
.status-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 10px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    border: 1px solid transparent;
}

/* KPI cards (Overview) */
.kpi-card {
    border-radius: 10px;
    border: 1px solid;
    padding: 14px 16px;
    cursor: pointer;
    transition: box-shadow 0.15s ease;
}
.kpi-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.kpi-card .kpi-value { font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800; font-size: 1.6rem; line-height: 1.1; }
.kpi-card .kpi-label { font-weight: 600; font-size: 0.85rem; margin-top: 4px; }
.kpi-card .kpi-sub { font-size: 0.72rem; margin-top: 2px; opacity: 0.75; }

/* Attention cards */
.attention-card {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border-radius: 8px;
    border: 1px solid;
    margin-bottom: 8px;
}
.attention-card .attention-title { font-weight: 600; font-size: 0.85rem; }
.attention-card .attention-desc { font-size: 0.75rem; margin-top: 2px; line-height: 1.4; opacity: 0.85; }

/* Workflow stage pills */
.workflow-stage-num {
    width: 30px; height: 30px; border-radius: 999px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.75rem;
    flex-shrink: 0;
}

/* Timeline (certificate status history) */
.timeline-row { display: flex; gap: 10px; }
.timeline-dot {
    width: 22px; height: 22px; border-radius: 999px; border: 2px solid;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.timeline-line { width: 1px; flex: 1; margin: 2px 0; min-height: 24px; }

/* Slide-out drawer: Streamlit's st.dialog only offers a centered modal
   ("Streamlit has no true slide-out panel" — see app/main.py's docstring),
   so this restyles that same centered-dialog DOM (confirmed via direct
   inspection: div[data-testid="stDialog"] > div is the full-viewport
   backdrop/centering flexbox, and div[role="dialog"] is the actual panel)
   into a right-anchored, full-height panel instead. It is still a modal
   underneath — Streamlit gives no way to make it non-blocking — but visually
   it reads as a drawer, not a centered dialog stealing the whole screen. */
div[data-testid="stDialog"] > div {
    align-items: stretch !important;
    justify-content: flex-end !important;
}
div[role="dialog"] {
    position: relative;
    top: 0 !important;
    height: 100vh !important;
    max-height: 100vh !important;
    width: 520px !important;
    max-width: 92vw !important;
    margin: 0 !important;
    border-radius: 0 !important;
    overflow-y: auto !important;
    animation: bir-drawer-slide-in 0.2s ease-out;
}
@keyframes bir-drawer-slide-in {
    from { transform: translateX(32px); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}

/* Sidebar is always dark regardless of app theme (matches the source
   design's fixed bg-sidebar) — these selectors are more specific than the
   theme block's global button rules, so they win regardless of load order. */
[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="secondary"] {
    background-color: transparent !important;
    border-color: transparent !important;
    color: #94A3B8 !important;
    justify-content: flex-start;
}
[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="secondary"]:hover {
    background-color: #1E293B !important;
    color: #E2E8F0 !important;
}
[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {
    background-color: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    justify-content: flex-start;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #64748B !important; }
[data-testid="stSidebar"] hr { border-color: #1E293B !important; }
</style>
"""


def page_tokens(theme: str) -> dict:
    """The active theme's color tokens, for views building custom HTML
    (KPI cards, timelines, badges) — the counterpart to `inject_css`."""
    return DARK if theme == "dark" else LIGHT


def status_colors(theme: str) -> dict:
    """The active theme's (bg, fg, border) tuples per badge variant."""
    return STATUS_DARK if theme == "dark" else STATUS_LIGHT


def inject_css(theme: str = "light") -> None:
    tokens = DARK if theme == "dark" else LIGHT
    st.markdown(_STATIC_CSS, unsafe_allow_html=True)
    st.markdown(f"<style>{_theme_css(tokens, theme == 'dark')}</style>", unsafe_allow_html=True)
