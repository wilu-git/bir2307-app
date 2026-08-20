"""Shared page-based pagination control — the same Previous/Next pattern
already used by the Audit Log (app/ui/views/more.py), reused here so the
Certificates and Payees tables page their results too instead of loading
every matching row into one table.
"""

from __future__ import annotations

import streamlit as st


def paginate(total_count: int, page_size: int, state_key: str) -> int:
    """Renders a "Showing a-b of N" caption plus Previous/Next controls,
    reading/writing the current page number at `st.session_state[state_key]`
    (1-based). Returns that page number so the caller can slice its rows.
    """
    st.session_state.setdefault(state_key, 1)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = min(st.session_state[state_key], total_pages)
    st.session_state[state_key] = page

    start = (page - 1) * page_size + 1
    end = min(page * page_size, total_count)

    cap_col, prev_col, label_col, next_col = st.columns([5, 0.6, 1, 0.6])
    with cap_col:
        st.caption(f"Showing {start}-{end} of {total_count}" if total_count else "No results")
    with prev_col:
        if st.button("⬅", key=f"{state_key}_prev", disabled=page <= 1, use_container_width=True):
            st.session_state[state_key] = page - 1
            st.rerun()
    with label_col:
        st.markdown(
            f'<div style="text-align:center;font-size:0.82rem;padding-top:6px;">Page {page} of {total_pages}</div>',
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button("➡", key=f"{state_key}_next", disabled=page >= total_pages, use_container_width=True):
            st.session_state[state_key] = page + 1
            st.rerun()
    return page


def reset_if_filters_changed(state_key: str, filters_key: tuple) -> None:
    """Resets `state_key`'s page number to 1 whenever `filters_key` (a
    tuple of the current filter values) differs from last render's —
    otherwise changing a filter could land you on a now out-of-range page
    showing nothing, with no obvious reason why."""
    tracker_key = f"{state_key}_filters_key"
    if st.session_state.get(tracker_key) != filters_key:
        st.session_state[state_key] = 1
        st.session_state[tracker_key] = filters_key
