"""Central st.session_state schema for the 3-pane workspace.

Every key the workspace reads/writes is defaulted here, once, so no tab
module has to guess whether a key already exists — Streamlit reruns the
whole script on every interaction, so relying on local variables would
lose selection/navigation state on the next rerun.
"""

from __future__ import annotations

import streamlit as st

_DEFAULTS = {
    "active_tab": "uploads",
    "selected_certificate": None,
    "selected_upload": None,
    "selected_search_result": None,
    "selected_log": None,
    "search_query": {"name": "", "tin": "", "date_range": (), "status": "(all)"},
    "search_page": 1,
    "logs_page": 1,
    "logs_filters": {"category": "(all)", "severity": "(all)", "unresolved_only": True},
}


def init_session_state() -> None:
    for key, default in _DEFAULTS.items():
        st.session_state.setdefault(key, default)
