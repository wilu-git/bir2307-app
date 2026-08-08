"""Uploads tab: import a workbook, browse past import batches.

There is no separate "uploaded files" table — `ImportBatch` rows are the
only reliable, complete upload history (the raw workbook bytes are also
written to disk under settings.uploads_dir, but keyed only by filename
with no dedup/versioning, so a same-named re-upload silently overwrites
the previous copy — a preexisting behavior this redesign doesn't change).
The middle-panel list is therefore built from ImportBatch rows.

The column-mapping step lets the user tell the importer which detected
spreadsheet column feeds which internal field, instead of relying purely
on the hardcoded `COLUMN_MAP`. Choosing "(default mapping)" and leaving
every suggestion as-is reproduces exactly today's behavior.
"""

from __future__ import annotations

import io
from collections import Counter

import streamlit as st

from app.config import settings
from app.core.import_excel import (
    COLUMN_MAP,
    DEFAULT_SHEET_NAME,
    MANDATORY_FIELDS,
    detect_headers,
    import_workbook,
)
from app.core.mapping_profiles import INTERNAL_FIELDS, list_profiles, save_profile, suggest_mapping
from app.core.models import EventLog, EventSeverity, ImportBatch
from app.ui.components.cards import render_selectable_card

_UNMAPPED = "(unmapped)"
_DEFAULT_PROFILE_CHOICE = "(default mapping)"


def _resolve_mapping_editor(session, detected_headers: list[str], sheet_name: str) -> dict[str, str]:
    """Renders the per-header mapping selectboxes; returns the currently
    chosen mapping (headers mapped to `_UNMAPPED` are excluded)."""
    profiles = list_profiles(session)
    profile_names = [p.name for p in profiles]
    profile_choice = st.selectbox(
        "Load saved profile",
        options=[_DEFAULT_PROFILE_CHOICE] + profile_names,
        key="mapping_profile_choice",
        help="Pick a previously-saved mapping, or start from the default and adjust below.",
    )

    if profile_choice == _DEFAULT_PROFILE_CHOICE:
        baseline: dict[str, str] = dict(COLUMN_MAP)
    else:
        baseline = dict(next(p for p in profiles if p.name == profile_choice).mapping)

    suggestions = suggest_mapping(detected_headers, profiles)

    st.caption(
        "One dropdown per column found in the sheet. Required fields "
        f"({', '.join(sorted(MANDATORY_FIELDS))}) must each be assigned to exactly one column."
    )

    current_mapping: dict[str, str] = {}
    for header in detected_headers:
        default_field = baseline.get(header) or suggestions.get(header)
        options = [_UNMAPPED] + INTERNAL_FIELDS
        default_index = options.index(default_field) if default_field in options else 0
        chosen = st.selectbox(
            f'"{header}"',
            options=options,
            index=default_index,
            key=f"colmap_{header}",
        )
        if chosen != _UNMAPPED:
            current_mapping[header] = chosen

    with st.expander("Save this mapping as a reusable profile"):
        profile_name = st.text_input("Profile name", key="mapping_profile_name")
        if st.button("Save mapping as profile", key="save_mapping_profile"):
            if not profile_name.strip():
                st.error("Give the profile a name first.")
            else:
                save_profile(session, profile_name.strip(), sheet_name, current_mapping)
                session.commit()
                st.success(f'Saved profile "{profile_name.strip()}".')
                st.rerun()

    return current_mapping


def render_uploads_tab(session, current_user, middle, right) -> None:
    with middle:
        st.subheader("Uploads")

        with st.container(border=True):
            st.markdown("**Upload a new Excel export**")

            sheet_name = st.text_input(
                "Sheet name to import",
                value=DEFAULT_SHEET_NAME,
                help="The real Favor Church export is a multi-sheet workbook — only this "
                "one sheet is read.",
            )
            uploaded_file = st.file_uploader("Excel file (.xlsx or .xls)", type=["xlsx", "xls"])

            if uploaded_file is not None:
                size_mb = uploaded_file.size / (1024 * 1024)
                if size_mb > settings.max_upload_mb:
                    st.error(
                        f"File is {size_mb:.1f} MB, which exceeds the "
                        f"{settings.max_upload_mb} MB limit."
                    )
                else:
                    try:
                        detected_headers = detect_headers(
                            io.BytesIO(uploaded_file.getvalue()), sheet_name=sheet_name
                        )
                    except Exception as exc:
                        st.error(f'Could not read sheet "{sheet_name}": {exc}')
                        detected_headers = []

                    if detected_headers:
                        st.markdown("**Column mapping**")
                        current_mapping = _resolve_mapping_editor(session, detected_headers, sheet_name)

                        missing = sorted(MANDATORY_FIELDS - set(current_mapping.values()))
                        target_counts = Counter(current_mapping.values())
                        duplicates = sorted(
                            field for field, count in target_counts.items() if count > 1
                        )

                        if missing:
                            st.error(
                                "These required fields aren't mapped to any column yet: "
                                + ", ".join(missing)
                            )
                        if duplicates:
                            st.error(
                                "These fields are mapped to more than one column — pick just one each: "
                                + ", ".join(duplicates)
                            )

                        if st.button(
                            "Import this file",
                            type="primary",
                            disabled=bool(missing or duplicates),
                        ):
                            dest = settings.uploads_dir / uploaded_file.name
                            dest.write_bytes(uploaded_file.getvalue())
                            with st.spinner(f'Importing sheet "{sheet_name}"...'):
                                batch = import_workbook(
                                    session,
                                    dest,
                                    filename=uploaded_file.name,
                                    uploaded_by=current_user,
                                    sheet_name=sheet_name,
                                    column_map=current_mapping,
                                )
                            st.session_state["selected_upload"] = batch.id
                            st.rerun()

        batches = session.query(ImportBatch).order_by(ImportBatch.id.desc()).all()
        st.caption(f"{len(batches)} past upload(s)")

        with st.container(height=420, key="uploads_list"):
            for batch in batches:
                clean = batch.error_count == 0
                clicked = render_selectable_card(
                    title=batch.filename,
                    subtitle=(
                        f"{batch.uploaded_at:%Y-%m-%d %H:%M} · {batch.row_count} rows · "
                        f"{batch.success_count} ok"
                    ),
                    badge=("clean", "success") if clean else (f"{batch.error_count} errors", "error"),
                    is_selected=st.session_state["selected_upload"] == batch.id,
                    key=f"batch_{batch.id}",
                    list_id="uploads",
                )
                if clicked:
                    st.session_state["selected_upload"] = batch.id
                    st.rerun()

    with right:
        batch_id = st.session_state["selected_upload"]
        if not batch_id:
            st.info("Select an upload to see its details.")
            return
        batch = session.get(ImportBatch, batch_id)
        if batch is None:
            st.warning("That upload no longer exists.")
            st.session_state["selected_upload"] = None
            return

        st.subheader(f'"{batch.filename}"')
        st.caption(f"Uploaded by {batch.uploaded_by} on {batch.uploaded_at:%Y-%m-%d %H:%M:%S}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total rows", batch.row_count)
        c2.metric("Imported successfully", batch.success_count)
        c3.metric("Errors", batch.error_count)

        events = (
            session.query(EventLog)
            .filter(EventLog.batch_id == batch.id)
            .order_by(EventLog.severity.desc(), EventLog.id)
            .all()
        )
        if events:
            st.subheader(f"Warnings & errors ({len(events)})")
            icon = {EventSeverity.ERROR: "🔴", EventSeverity.WARNING: "🟡", EventSeverity.INFO: "🔵"}
            for event in events:
                with st.expander(f"{icon[event.severity]} [{event.category.value}] {event.message}"):
                    st.caption("Technical detail (developer-only — full, unmasked data):")
                    st.code(event.technical_detail or "(none)", language=None)
        else:
            st.success("No warnings or errors — every row imported cleanly.")
