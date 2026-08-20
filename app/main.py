"""Streamlit entrypoint: password gate, DB init, sidebar-shell workspace.

Single-script by design. Streamlit auto-renders its own sidebar page-nav
for anything under app/pages/, unconditionally — this app has no pages/
directory at all so its own chrome stays in full control. Navigation is a
persistent left sidebar (app/ui/nav.py) with five destinations (Overview,
Certificates, Payees, Reports, More); each view module renders the shared
top bar (app/ui/layout.py) then its own content. The "+ New Import"
workflow is a global modal (app/ui/workflows/import_wizard.py) reachable
from any view's top bar. Business logic still lives entirely in
app/core/ — this file and app/ui/*.py only wire widgets to it.
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
from app.ui.nav import render_sidebar
from app.ui.state import init_session_state
from app.ui.styles import inject_css
from app.ui.views.certificates import render_certificates_view
from app.ui.views.manual_form import render_manual_form_view
from app.ui.views.more import render_more_view
from app.ui.views.overview import render_overview_view
from app.ui.views.payees import render_payees_view
from app.ui.views.reports import render_reports_view
from app.ui.workflows.import_wizard import maybe_render_import_wizard

st.set_page_config(page_title="BIR 2307 Generator", page_icon="🧾", layout="wide")

configure_logging()
init_db()
current_user = require_login()

init_session_state()
inject_css(st.session_state["theme"])
render_sidebar()

_VIEW_RENDERERS = {
    "overview": render_overview_view,
    "certificates": render_certificates_view,
    "payees": render_payees_view,
    "reports": render_reports_view,
    "manual_form": render_manual_form_view,
    "more": render_more_view,
}

with SessionLocal() as session:
    _VIEW_RENDERERS[st.session_state["view"]](session, current_user)
    maybe_render_import_wizard(session, current_user)
