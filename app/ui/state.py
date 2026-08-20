"""Central st.session_state schema for the sidebar-shell workspace.

Every key the workspace reads/writes is defaulted here, once, so no view
module has to guess whether a key already exists — Streamlit reruns the
whole script on every interaction, so relying on local variables would
lose selection/navigation state on the next rerun.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.core.payees import quarter_bounds


def _current_quarter() -> tuple[int, int]:
    now = datetime.now()
    return now.year, (now.month - 1) // 3 + 1


_DEFAULTS = {
    "theme": "light",
    "view": "overview",
    "global_quarter": None,  # (year, quarter); None resolves to the real current quarter
    "global_search": "",
    # Certificates workspace
    "certificates_filters": {"search": "", "status": "(all)", "quarter": "(any)", "year": "(any)"},
    "certificates_selected_ids": set(),
    "selected_certificate_id": None,
    # Payees workspace
    "payees_search": "",
    "selected_payee_id": None,
    "payee_edit_mode": False,
    # More section
    "more_section": "audit",
    "logs_page": 1,
    "logs_filters": {"category": "(all)", "severity": "(all)", "unresolved_only": True},
    "payor_edit_mode": False,
    # Import wizard (opened from the top-bar "+ New Import" quick action)
    "import_wizard_open": False,
    "import_wizard_stage": "upload",
    "import_wizard_batch_id": None,
    "import_wizard_group_result": None,
    # Manual Form (blank BIR 2307, no database records created)
    "manual_form_last_path": None,
}


def init_session_state() -> None:
    for key, default in _DEFAULTS.items():
        st.session_state.setdefault(key, default)


def current_quarter_bounds() -> tuple[datetime, datetime]:
    """The globally-selected quarter's (period_start, period_end), or the
    real current calendar quarter if the user hasn't picked one."""
    year, quarter = st.session_state["global_quarter"] or _current_quarter()
    return quarter_bounds(year, quarter)


def current_quarter_label() -> str:
    year, quarter = st.session_state["global_quarter"] or _current_quarter()
    return f"Q{quarter} {year}"
