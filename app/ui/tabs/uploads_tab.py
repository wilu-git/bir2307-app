"""Uploads tab: import a workbook, browse past import batches.

There is no separate "uploaded files" table — `ImportBatch` rows are the
only reliable, complete upload history (the raw workbook bytes are also
written to disk under settings.uploads_dir, but keyed only by filename
with no dedup/versioning, so a same-named re-upload silently overwrites
the previous copy — a preexisting behavior this redesign doesn't change).
The middle-panel list is therefore built from ImportBatch rows.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.config import settings
from app.core.import_excel import COLUMN_MAP, DEFAULT_SHEET_NAME, import_workbook
from app.core.models import EventLog, EventSeverity, ImportBatch
from app.ui.components.cards import render_selectable_card


def render_uploads_tab(session, current_user, middle, right) -> None:
    with middle:
        st.subheader("Uploads")

        with st.container(border=True):
            st.markdown("**Upload a new Excel export**")
            with st.expander("Source column → stored field (click to view)"):
                mapping_df = pd.DataFrame(
                    [{"Source column": src, "Stored as": dst} for src, dst in COLUMN_MAP.items()]
                )
                st.dataframe(mapping_df, use_container_width=True, hide_index=True)
                st.caption(
                    "`Column 1`–`Column 16` are concatenated into notes; `a`, `Column 39`, "
                    "`FILE NAME`, and `Not Subject to EWT` are excluded, per the confirmed spec."
                )

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
                elif st.button("Import this file", type="primary"):
                    dest = settings.uploads_dir / uploaded_file.name
                    dest.write_bytes(uploaded_file.getvalue())
                    with st.spinner(f'Importing sheet "{sheet_name}"...'):
                        batch = import_workbook(
                            session,
                            dest,
                            filename=uploaded_file.name,
                            uploaded_by=current_user,
                            sheet_name=sheet_name,
                        )
                    st.session_state["selected_upload"] = batch.id
                    st.rerun()

        batches = session.query(ImportBatch).order_by(ImportBatch.id.desc()).all()
        st.caption(f"{len(batches)} past upload(s)")

        with st.container(height=420, key="middle_list"):
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
