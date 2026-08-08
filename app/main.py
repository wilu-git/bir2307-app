"""Streamlit entrypoint: password gate, DB init, and the tabbed workspace.

Single-script by design. Streamlit auto-renders its own sidebar page-nav
for anything under app/pages/, unconditionally — this app has no pages/
directory at all so its own chrome stays in full control. Navigation is
native `st.tabs()` (there is no sidebar); each of the three sections
(Payees, Uploads, Logs) renders into its own 2-pane (list/detail) layout.
Business logic still lives entirely in app/core/ — this file and
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
from app.ui.layout import render_app_header, render_two_pane
from app.ui.nav import render_top_tabs
from app.ui.state import init_session_state
from app.ui.styles import inject_css
from app.ui.tabs.logs_tab import render_logs_tab
from app.ui.tabs.payees_tab import render_payees_tab
from app.ui.tabs.uploads_tab import render_uploads_tab

st.set_page_config(page_title="BIR 2307 Generator", page_icon="🧾", layout="wide")

configure_logging()
init_db()
current_user = require_login()

init_session_state()
inject_css()
render_app_header()

with SessionLocal() as session:
    tab_payees, tab_uploads, tab_logs = render_top_tabs()

    with tab_payees:
        list_col, detail_col = render_two_pane()
        render_payees_tab(session, current_user, list_col, detail_col)

    with tab_uploads:
        list_col, detail_col = render_two_pane()
        render_uploads_tab(session, current_user, list_col, detail_col)

    with tab_logs:
        list_col, detail_col = render_two_pane()
        render_logs_tab(session, current_user, list_col, detail_col)