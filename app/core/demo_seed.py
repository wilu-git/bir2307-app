"""Synthetic demo data for a client-facing deployment.

Never used for the real Favor Church deployment — gated behind
`settings.demo_mode` (env var `DEMO_MODE=true`) and only ever runs against
an empty database, so there is no code path where this can overwrite real
payee/transaction records. All names, TINs, and addresses below are made
up for demonstration purposes only.

Rather than hand-building Payee/Transaction rows directly, this builds an
in-memory "Excel upload" and runs it through the real `import_workbook()`
pipeline — the demo then exercises the actual validation, mismatch
detection, duplicate handling, and logging a real upload would, instead of
a hollow shortcut that looks right but proves nothing.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.core.certificates import group_ungrouped_transactions, transition_status
from app.core.import_excel import DEFAULT_SHEET_NAME, import_workbook
from app.core.models import Certificate, CertificateStatus, Payee, Payor
from app.core.pdf_generator import generate_certificate_pdf

DEMO_PAYOR = {
    "tin": "000-111-222-000",
    "registered_name": "Sample Ministries Foundation Inc. (DEMO DATA)",
    "address": "123 Demo Avenue, Sample City, Metro Manila",
    "zip_code": "1000",
}

# Deliberately exercises every event_logs category the real importer can
# raise: a malformed TIN, an unknown ATC code, an accidental duplicate BILL
# NO., a legitimate multi-row BILL NO. merge, a computation mismatch, and
# an ambiguous signed/not-signed status — so the Logs page looks realistic
# rather than empty.
_DEMO_ROWS = [
    # reference_no, tin, name, address, zip, email, atc, vat, total, gross, upl_paid, upl_base, upl_tax, status_text, assigned, date, remarks, signed, not_signed
    (
        "DEMO-1001",
        "100-200-300-001",
        "Juan Dela Cruz",
        "12 Sample St, Quezon City",
        "1100",
        "juan@example.com",
        "WI050",
        "NONVAT",
        20000,
        20000,
        19000,
        20000,
        1000,
        "Completed",
        "Staff A",
        "2026-02-10",
        "Consulting fee",
        False,
        False,
    ),
    (
        "DEMO-1002",
        "100-200-300-001",
        "Juan Dela Cruz",
        "12 Sample St, Quezon City",
        "1100",
        "juan@example.com",
        "WI050",
        "NONVAT",
        15000,
        15000,
        14250,
        15000,
        750,
        "Forwarded to BIR",
        "Staff A",
        "2026-05-14",
        "Consulting fee",
        False,
        True,
    ),
    (
        "DEMO-2001",
        "200-300-400-002",
        "Maria Santos Consultancy",
        "45 Example Ave, Makati",
        "1200",
        "maria@example.com",
        "WI051",
        "NONVAT",
        50000,
        50000,
        45000,
        50000,
        5000,
        "Not started",
        "Staff B",
        "2026-02-20",
        "Technical consulting",
        False,
        True,
    ),
    # Legitimate merge: same BILL NO., different amounts -> two transactions, one certificate.
    (
        "DEMO-2001",
        "200-300-400-002",
        "Maria Santos Consultancy",
        "45 Example Ave, Makati",
        "1200",
        "maria@example.com",
        "WI051",
        "NONVAT",
        8000,
        8000,
        7200,
        8000,
        800,
        "Not started",
        "Staff B",
        "2026-02-25",
        "Follow-up session",
        False,
        True,
    ),
    (
        "DEMO-3001",
        "300-400-500-003",
        "Alpha Trading Corp",
        "78 Placeholder Rd, Pasig",
        "1600",
        "billing@example.com",
        "WC100",
        "VAT",
        112000,
        112000,
        105300,
        100500,
        5000,
        "Completed",
        "Staff A",
        "2026-03-05",
        "Office space rental",
        True,
        False,
    ),
    (
        "DEMO-3002",
        "300-400-500-003",
        "Alpha Trading Corp",
        "78 Placeholder Rd, Pasig",
        "1600",
        "billing@example.com",
        "WC100",
        "VAT",
        56000,
        56000,
        53200,
        None,
        None,
        "Completed",
        "Staff A",
        "2026-05-05",
        "Office space rental",
        True,
        False,
    ),
    (
        "DEMO-4001",
        "400-500-600-004",
        "Bright Star Supplies Inc.",
        "9 Trading Blvd, Mandaluyong",
        "1550",
        "sales@example.com",
        "WC158",
        "VAT",
        30000,
        30000,
        29700,
        None,
        None,
        "",
        "Staff B",
        "2026-03-18",
        "Office supplies",
        True,
        True,
    ),
    (
        "DEMO-4002",
        "400-500-600-004",
        "Bright Star Supplies Inc.",
        "9 Trading Blvd, Mandaluyong",
        "1550",
        "sales@example.com",
        "WC158",
        "VAT",
        18000,
        18000,
        17820,
        None,
        None,
        "Forwarded",
        "Staff B",
        "2026-06-02",
        "Office supplies",
        False,
        True,
    ),
    (
        "DEMO-5001",
        "500-600-700-005",
        "Dela Cruz Contractors",
        "21 Contractor Ln, Taguig",
        "1630",
        "info@example.com",
        "WC120",
        "NONVAT",
        40000,
        40000,
        39200,
        None,
        None,
        "Not started",
        "Staff A",
        "2026-04-01",
        "Renovation works",
        False,
        True,
    ),
    (
        "DEMO-5002",
        "500-600-700-005",
        "Dela Cruz Contractors",
        "21 Contractor Ln, Taguig",
        "1630",
        "info@example.com",
        "ZZZ99",
        "NONVAT",
        12000,
        12000,
        11760,
        None,
        None,
        "Not started",
        "Staff A",
        "2026-04-15",
        "Unknown ATC demo row",
        False,
        True,
    ),
    (
        "DEMO-6001",
        "600-700-800-006",
        "Green Fields Services",
        "33 Service Rd, Paranaque",
        "1700",
        "contact@example.com",
        "WC160",
        "VAT",
        67200,
        67200,
        63840,
        None,
        None,
        "Completed",
        "Staff B",
        "2026-04-20",
        "Landscaping services",
        True,
        False,
    ),
    (
        "DEMO-7001",
        "70-80-90",
        "Sample Freelancer",
        "5 Demo Lane, Marikina",
        "1800",
        "freelancer@example.com",
        "WI100",
        "NONVAT",
        10000,
        10000,
        9500,
        None,
        None,
        "Not started",
        "Staff A",
        "2026-05-01",
        "Malformed-TIN demo row",
        False,
        True,
    ),
    # Accidental duplicate: identical amounts + date under the same BILL NO. -> collapsed to one.
    (
        "DEMO-8001",
        "700-800-900-007",
        "Sunrise Nonprofit Partners",
        "88 Example Cir, San Juan",
        "1500",
        "hello@example.com",
        "WI160",
        "NONVAT",
        25000,
        25000,
        24500,
        None,
        None,
        "Completed",
        "Staff B",
        "2026-05-10",
        "Program services",
        True,
        False,
    ),
    (
        "DEMO-8001",
        "700-800-900-007",
        "Sunrise Nonprofit Partners",
        "88 Example Cir, San Juan",
        "1500",
        "hello@example.com",
        "WI160",
        "NONVAT",
        25000,
        25000,
        24500,
        None,
        None,
        "Completed",
        "Staff B",
        "2026-05-10",
        "Program services",
        True,
        False,
    ),
]

_COLUMNS = [
    "BILL NO.",
    "TIN NUMBER",
    "CORPORATE NAME",
    "CORPORATE ADDRESS",
    "ZIP CODE",
    "Corporate Email Address",
    "TAX CODE",
    "VAT / NONVAT",
    "Total Billing",
    "GROSS AMOUNT",
    "AMOUNT PAID",
    "Amount at 2307",
    "TAX WITHHELD",
    "Status",
    "Assigned to",
    "Date Accomplished",
    "Remarks",
    "Signed Copy Google Drive",
    "NOT SIGNED",
]


def _build_demo_workbook() -> BytesIO:
    df = pd.DataFrame(_DEMO_ROWS, columns=_COLUMNS)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=DEFAULT_SHEET_NAME, index=False)
    buf.seek(0)
    return buf


def seed_demo_data(session: Session) -> None:
    """Populate an empty database with synthetic demo data.

    No-ops unless `settings.demo_mode` is set AND the database has no
    payees yet — never touches a database that already has real data.
    """
    if not settings.demo_mode:
        return
    if session.query(Payee).count() > 0:
        return

    payor = session.query(Payor).first()
    if payor is not None:
        payor.tin = DEMO_PAYOR["tin"]
        payor.registered_name = DEMO_PAYOR["registered_name"]
        payor.address = DEMO_PAYOR["address"]
        payor.zip_code = DEMO_PAYOR["zip_code"]
        session.commit()

    workbook = _build_demo_workbook()
    import_workbook(session, workbook, "demo_sample_data.xlsx", "demo_seed")

    group_ungrouped_transactions(session)

    # Generate an unsigned PDF for a couple of certificates and move a few
    # through their status lifecycle, so the Certificates page shows a
    # realistic mix instead of everything sitting in "draft".
    certs = session.query(Certificate).order_by(Certificate.id).all()
    for cert in certs[:2]:
        try:
            generate_certificate_pdf(session, cert, settings.generated_pdfs_dir)
            if cert.status == CertificateStatus.DRAFT:
                transition_status(
                    session,
                    cert,
                    CertificateStatus.GENERATED,
                    "demo_seed",
                    "Demo data.",
                )
        except Exception:
            pass
    session.commit()
