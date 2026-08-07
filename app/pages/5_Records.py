"""Records page: edit the payor record and payee records in-app.

Before this page existed, correcting the seeded placeholder payor or a
mis-imported payee required a direct database edit (see the README's old
"Required first step" instructions). Thin by design, per the other pages —
validation, diffing, and logging live in app/core/records.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Pages run as independent top-level scripts on Streamlit Cloud, so each
# needs the project root on sys.path for the `app.*` imports below.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.core.auth import require_login
from app.core.db import SessionLocal, init_db
from app.core.logging_config import configure_logging
from app.core.models import Payor, TaxType
from app.core.records import (
    DuplicateTinError,
    PayeeFields,
    PayorFields,
    search_payees,
    update_payee,
    update_payor,
)
from app.core.security import mask_tin

configure_logging()
init_db()
current_user = require_login()

st.title("Records")

with SessionLocal() as session:
    st.header("Payor")
    payor = session.query(Payor).first()
    if payor is not None:
        if "PLACEHOLDER" in payor.tin or "PLACEHOLDER" in (payor.registered_name or ""):
            st.warning(
                "This is still the placeholder payor. Every certificate PDF prints these "
                "values as the withholding agent — replace them before issuing any real "
                "certificate."
            )
        with st.form("edit_payor"):
            tin = st.text_input("TIN", value=payor.tin)
            registered_name = st.text_input(
                "Registered name", value=payor.registered_name
            )
            address = st.text_area("Address", value=payor.address or "")
            zip_code = st.text_input("ZIP code", value=payor.zip_code or "")
            if st.form_submit_button("Save payor", type="primary"):
                update_payor(
                    session,
                    payor,
                    PayorFields(
                        tin=tin,
                        registered_name=registered_name,
                        address=address,
                        zip_code=zip_code,
                    ),
                    current_user,
                )
                session.commit()
                st.success("Payor record updated.")
                st.rerun()
    else:
        st.error("No payor record found.")

    st.divider()
    st.header("Payees")

    col_name, col_tin = st.columns(2)
    name_filter = col_name.text_input("Search by name")
    tin_filter = col_tin.text_input("Search by TIN")
    payees = search_payees(session, name=name_filter, tin=tin_filter)
    st.caption(f"{len(payees)} payee(s)")

    for payee in payees:
        with st.expander(f"{payee.registered_name} — {mask_tin(payee.tin)}"):
            with st.form(f"edit_payee_{payee.id}"):
                tin = st.text_input("TIN", value=payee.tin, key=f"tin_{payee.id}")
                registered_name = st.text_input(
                    "Registered name",
                    value=payee.registered_name,
                    key=f"name_{payee.id}",
                )
                address = st.text_area(
                    "Address", value=payee.address or "", key=f"addr_{payee.id}"
                )
                zip_code = st.text_input(
                    "ZIP code", value=payee.zip_code or "", key=f"zip_{payee.id}"
                )
                email = st.text_input(
                    "Email", value=payee.email or "", key=f"email_{payee.id}"
                )
                tax_type_options = [t.value for t in TaxType]
                tax_type = st.selectbox(
                    "Tax type",
                    options=tax_type_options,
                    index=tax_type_options.index(payee.tax_type.value),
                    key=f"tax_{payee.id}",
                )
                if st.form_submit_button("Save payee"):
                    try:
                        update_payee(
                            session,
                            payee,
                            PayeeFields(
                                tin=tin,
                                registered_name=registered_name,
                                address=address,
                                zip_code=zip_code,
                                email=email,
                                tax_type=TaxType(tax_type),
                            ),
                            current_user,
                        )
                        session.commit()
                        st.success("Payee record updated.")
                        st.rerun()
                    except DuplicateTinError as exc:
                        session.rollback()
                        st.error(str(exc))
