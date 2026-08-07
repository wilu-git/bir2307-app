"""Upload page: pick a workbook + sheet, preview the confirmed column
mapping, import, and show a post-upload summary banner with drill-down
into every warning/error raised during that batch.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.config import settings
from app.core.auth import require_login
from app.core.db import SessionLocal, init_db
from app.core.import_excel import COLUMN_MAP, DEFAULT_SHEET_NAME, import_workbook
from app.core.logging_config import configure_logging
from app.core.models import EventLog, EventSeverity

configure_logging()
init_db()
current_user = require_login()

st.title("Upload Excel Export")

st.subheader("Confirmed column mapping")
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
    help="The real Favor Church export is a multi-sheet workbook — only this one sheet is read.",
)

uploaded_file = st.file_uploader("Excel file (.xlsx or .xls)", type=["xlsx", "xls"])

if uploaded_file is not None:
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        st.error(f"File is {size_mb:.1f} MB, which exceeds the {settings.max_upload_mb} MB limit.")
    elif st.button("Import this file", type="primary"):
        dest = settings.uploads_dir / uploaded_file.name
        dest.write_bytes(uploaded_file.getvalue())

        with SessionLocal() as session:
            with st.spinner(f'Importing sheet "{sheet_name}"...'):
                batch = import_workbook(
                    session,
                    dest,
                    filename=uploaded_file.name,
                    uploaded_by=current_user,
                    sheet_name=sheet_name,
                )
            st.session_state["last_batch_id"] = batch.id

if st.session_state.get("last_batch_id"):
    with SessionLocal() as session:
        from app.core.models import ImportBatch

        batch = session.get(ImportBatch, st.session_state["last_batch_id"])
        if batch:
            st.subheader(f'Summary — "{batch.filename}"')
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
                for event in events:
                    icon = {
                        EventSeverity.ERROR: "🔴",
                        EventSeverity.WARNING: "🟡",
                        EventSeverity.INFO: "🔵",
                    }[event.severity]
                    with st.expander(f"{icon} [{event.category.value}] {event.message}"):
                        st.caption("Technical detail (developer-only — full, unmasked data):")
                        st.code(event.technical_detail or "(none)", language=None)
            else:
                st.success("No warnings or errors — every row imported cleanly.")
