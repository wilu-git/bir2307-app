"""The "+ New Import" guided workflow — the app's primary import surface.

Per the redesign spec, import/mapping/validation are not permanent nav
destinations; they're a contextual workflow opened from anywhere via the
top bar's "+ New Import" quick action. Three real stages, each backed by
an actual app/core/ call — no fabricated progress bars or invented
"generate N certificates in one click" step (the real backend keeps
importing transactions and grouping them into certificates as two
separate operations; this wizard runs both, back to back, but shows real
counts from each):

  01 Upload  — same file_uploader as before.
  02 Map     — the same compact 2-per-row column-mapping grid that used
               to be its own popup, inlined as a wizard stage instead.
  03 Import  — runs the real import_workbook() and shows the real
               Ready/Warnings/Errors counts from the event_logs it wrote.
  (complete) — runs group_ungrouped_transactions() and shows the real
               certificate count it touched.
"""

from __future__ import annotations

import io
from collections import Counter

import streamlit as st

from app.config import settings
from app.core.certificates import group_ungrouped_transactions
from app.core.import_excel import (
    COLUMN_MAP,
    DEFAULT_SHEET_NAME,
    MANDATORY_FIELDS,
    PDF_FIELDS,
    detect_headers,
    import_workbook,
)
from app.core.mapping_profiles import INTERNAL_FIELDS, list_profiles, save_profile, suggest_mapping
from app.core.models import EventLog, EventSeverity, ImportBatch

_UNMAPPED = "(unmapped)"
_DEFAULT_PROFILE_CHOICE = "(default mapping)"
_STAGES = [("upload", "Upload", 1), ("map", "Map", 2), ("import", "Import", 3)]


def _close() -> None:
    st.session_state["import_wizard_open"] = False
    st.session_state["import_wizard_stage"] = "upload"
    st.session_state["import_wizard_batch_id"] = None
    st.session_state["import_wizard_group_result"] = None


def _stage_tabs(current: str) -> None:
    cols = st.columns(len(_STAGES))
    for col, (key, label, number) in zip(cols, _STAGES):
        done = [s[0] for s in _STAGES].index(current) > [s[0] for s in _STAGES].index(key)
        marker = "✓" if done else str(number)
        style = "font-weight:700;" if key == current else ""
        col.markdown(f"<span style='{style}'>{marker}. {label}</span>", unsafe_allow_html=True)


def _mapping_defaults(detected_headers, profiles, profile_choice) -> dict:
    if profile_choice == _DEFAULT_PROFILE_CHOICE:
        baseline = {h: f for h, f in COLUMN_MAP.items() if f in PDF_FIELDS}
    else:
        baseline = dict(next(p for p in profiles if p.name == profile_choice).mapping)
    suggestions = suggest_mapping(detected_headers, profiles)
    return {h: baseline.get(h) or suggestions.get(h) for h in detected_headers}


@st.dialog("New Import", width="large")
def _import_wizard_dialog(session, current_user: str) -> None:
    stage = st.session_state["import_wizard_stage"]

    if stage != "complete":
        _stage_tabs(stage)
        st.divider()

    if stage == "upload":
        st.caption("Import Excel transactions and generate BIR 2307 certificates.")
        sheet_name = st.text_input(
            "Sheet name to import",
            value=st.session_state.get("import_wizard_sheet_name", DEFAULT_SHEET_NAME),
            key="wizard_sheet_name",
            help="The real Favor Church export is a multi-sheet workbook — only this one sheet is read.",
        )
        uploaded_file = st.file_uploader("Excel file (.xlsx or .xls)", type=["xlsx", "xls"], key="wizard_file")

        col_cancel, col_next = st.columns([1, 1])
        if col_cancel.button("Cancel", key="wizard_cancel_upload"):
            _close()
            st.rerun()
        if uploaded_file is not None:
            size_mb = uploaded_file.size / (1024 * 1024)
            if size_mb > settings.max_upload_mb:
                st.error(f"File is {size_mb:.1f} MB, which exceeds the {settings.max_upload_mb} MB limit.")
            elif col_next.button("Continue to Mapping", type="primary", key="wizard_to_map"):
                try:
                    headers = detect_headers(io.BytesIO(uploaded_file.getvalue()), sheet_name=sheet_name)
                except Exception as exc:
                    st.error(f'Could not read sheet "{sheet_name}": {exc}')
                    headers = []
                if headers:
                    st.session_state["import_wizard_file_bytes"] = uploaded_file.getvalue()
                    st.session_state["import_wizard_file_name"] = uploaded_file.name
                    st.session_state["import_wizard_sheet_name"] = sheet_name
                    st.session_state["import_wizard_headers"] = headers
                    st.session_state["import_wizard_stage"] = "map"
                    st.rerun()
                else:
                    st.error("No columns detected in that sheet.")

    elif stage == "map":
        headers = st.session_state["import_wizard_headers"]
        sheet_name = st.session_state["import_wizard_sheet_name"]
        profiles = list_profiles(session)
        profile_choice = st.selectbox(
            "Load saved profile",
            options=[_DEFAULT_PROFILE_CHOICE] + [p.name for p in profiles],
            key="wizard_profile_choice",
        )
        if st.button("Reset to suggested mapping", key="wizard_reset_mapping"):
            for header in headers:
                st.session_state.pop(f"wizard_colmap_{header}", None)

        defaults = _mapping_defaults(headers, profiles, profile_choice)
        mapped_count = sum(1 for h in headers if defaults.get(h))
        st.caption(f"{mapped_count} / {len(headers)} fields auto-matched or previously saved.")

        options = [_UNMAPPED] + INTERNAL_FIELDS
        current_mapping: dict[str, str] = {}
        grid = st.columns(2)
        for i, header in enumerate(headers):
            default_field = defaults.get(header)
            default_index = options.index(default_field) if default_field in options else 0
            with grid[i % 2]:
                chosen = st.selectbox(f'"{header}"', options=options, index=default_index, key=f"wizard_colmap_{header}")
            if chosen != _UNMAPPED:
                current_mapping[header] = chosen

        missing = sorted(MANDATORY_FIELDS - set(current_mapping.values()))
        duplicates = sorted(f for f, n in Counter(current_mapping.values()).items() if n > 1)
        if missing:
            st.error("These required fields aren't mapped to any column yet: " + ", ".join(missing))
        if duplicates:
            st.error("These fields are mapped to more than one column — pick just one each: " + ", ".join(duplicates))

        with st.expander("Save this mapping as a reusable profile"):
            profile_name = st.text_input("Profile name", key="wizard_profile_name")
            if st.button("Save mapping as profile", key="wizard_save_profile"):
                if not profile_name.strip():
                    st.error("Give the profile a name first.")
                else:
                    save_profile(session, profile_name.strip(), sheet_name, current_mapping)
                    session.commit()
                    st.success(f'Saved profile "{profile_name.strip()}".')

        col_back, col_next = st.columns([1, 1])
        if col_back.button("Back", key="wizard_back_to_upload"):
            st.session_state["import_wizard_stage"] = "upload"
            st.rerun()
        if col_next.button(
            "Continue to Import", type="primary", disabled=bool(missing or duplicates), key="wizard_to_import"
        ):
            st.session_state["import_wizard_mapping"] = current_mapping
            st.session_state["import_wizard_stage"] = "import"
            st.rerun()

    elif stage == "import":
        if st.session_state["import_wizard_batch_id"] is None:
            file_bytes = st.session_state["import_wizard_file_bytes"]
            file_name = st.session_state["import_wizard_file_name"]
            sheet_name = st.session_state["import_wizard_sheet_name"]
            mapping = st.session_state["import_wizard_mapping"]
            dest = settings.uploads_dir / file_name
            with st.spinner(f'Importing sheet "{sheet_name}"...'):
                dest.write_bytes(file_bytes)
                batch = import_workbook(
                    session, dest, filename=file_name, uploaded_by=current_user, sheet_name=sheet_name, column_map=mapping
                )
            st.session_state["import_wizard_batch_id"] = batch.id
            st.rerun()

        batch = session.get(ImportBatch, st.session_state["import_wizard_batch_id"])
        events = session.query(EventLog).filter(EventLog.batch_id == batch.id).all()
        errors = [e for e in events if e.severity == EventSeverity.ERROR]
        warnings = [e for e in events if e.severity == EventSeverity.WARNING]

        st.markdown("**Your file is ready to review**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total rows", batch.row_count)
        m2.metric("Imported", batch.success_count)
        m3.metric("Warnings", len(warnings))
        m4.metric("Errors", len(errors))

        if errors:
            with st.expander(f"{len(errors)} error(s)", expanded=True):
                for e in errors[:20]:
                    st.error(e.message)
        if warnings:
            with st.expander(f"{len(warnings)} warning(s)"):
                for w in warnings[:20]:
                    st.warning(w.message)
        if not errors and not warnings:
            st.success("No warnings or errors — every row imported cleanly.")

        col_cancel, col_next = st.columns([1, 1])
        if col_cancel.button("Return to Overview", key="wizard_return_after_import"):
            _close()
            st.session_state["view"] = "overview"
            st.rerun()
        if col_next.button("Group into certificates & finish", type="primary", key="wizard_group"):
            with st.spinner("Grouping transactions into certificates..."):
                touched = group_ungrouped_transactions(session)
            st.session_state["import_wizard_group_result"] = len(touched)
            st.session_state["import_wizard_stage"] = "complete"
            st.rerun()

    elif stage == "complete":
        touched = st.session_state["import_wizard_group_result"] or 0
        st.markdown(f"### {touched} certificate(s) created or updated")
        st.caption("Import complete — new transactions have been grouped into draft certificates.")
        col_a, col_b, col_c = st.columns(3)
        if col_a.button("Review Certificates", type="primary", key="wizard_review_certs"):
            _close()
            st.session_state["view"] = "certificates"
            st.rerun()
        if col_b.button("Import Another File", key="wizard_import_again"):
            st.session_state["import_wizard_stage"] = "upload"
            st.session_state["import_wizard_batch_id"] = None
            st.session_state["import_wizard_group_result"] = None
            st.rerun()
        if col_c.button("Return to Overview", key="wizard_return_complete"):
            _close()
            st.session_state["view"] = "overview"
            st.rerun()


def maybe_render_import_wizard(session, current_user: str) -> None:
    if st.session_state["import_wizard_open"]:
        _import_wizard_dialog(session, current_user)
