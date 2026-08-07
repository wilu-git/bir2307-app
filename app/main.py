"""Streamlit entrypoint: password gate, DB init, and the 3-pane workspace.

Single-script by design. Streamlit auto-renders its own sidebar page-nav
for anything under app/pages/, unconditionally — that can't coexist with
an in-page left-nav being the primary navigation, so this app has no
pages/ directory at all. All four sections (Uploads, Certificates, Search,
Logs) are dispatched from here based on st.session_state["active_tab"],
each rendering into the middle/right columns of one persistent 3-pane
layout. Business logic still lives entirely in app/core/ — this file and
app/ui/*.py only wire widgets to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit only puts this script's own directory on sys.path, so the
# project root (needed for the `app.*` absolute imports below) has to be
# added explicitly — otherwise this fails with "No module named 'app'"
# on Streamlit Cloud, where we don't control how the interpreter is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.core.auth import require_login
from app.core.db import SessionLocal, init_db
from app.core.logging_config import configure_logging
from app.ui.layout import render_app_header, render_three_pane
from app.ui.nav import render_left_nav
from app.ui.state import init_session_state
from app.ui.styles import inject_css
from app.ui.tabs.certificates_tab import render_certificates_tab
from app.ui.tabs.logs_tab import render_logs_tab
from app.ui.tabs.search_tab import render_search_tab
from app.ui.tabs.uploads_tab import render_uploads_tab

st.set_page_config(page_title="BIR 2307 Generator", page_icon="🧾", layout="wide")

configure_logging()
init_db()
current_user = require_login()

init_session_state()
inject_css()
render_app_header()

with SessionLocal() as session:
    left, middle, right = render_three_pane()
    with left:
        render_left_nav()

    tab = st.session_state["active_tab"]
    if tab == "uploads":
        render_uploads_tab(session, current_user, middle, right)
    elif tab == "certificates":
        render_certificates_tab(session, current_user, middle, right)
    elif tab == "search":
        render_search_tab(session, middle, right)
    elif tab == "logs":
        render_logs_tab(session, current_user, middle, right)