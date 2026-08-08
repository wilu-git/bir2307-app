"""BIR Form 2307 certificate PDF rendering.

Per the user's explicit instruction, this overlays computed values onto
page 1 of the real official form (`app/assets/bir2307_official_template.pdf`,
sourced from bir.gov.ph/bir-forms) rather than reconstructing the layout —
the template file itself is never modified, only copied once as a static
asset. A transparent reportlab overlay (same page size) is merged onto a
fresh copy of the template page for every certificate, via pypdf.

Only page 1 of the template is used — page 2 is the ATC-code reference
schedule, not part of the issued certificate itself.

## Coordinates

Every position below was measured directly off the template's own vector
graphics with pdfplumber (`page.rects` / `page.lines`), not eyeballed from
a screenshot — the TIN and date fields are printed as individual per-digit
boxes, and the Part III table has real gridlines, so the coordinates here
are the template's actual box edges, not approximations. Re-measure with
the snippet below if the template file is ever replaced with a different
revision:

    import pdfplumber
    with pdfplumber.open(TEMPLATE_PATH) as pdf:
        page = pdf.pages[0]
        for r in page.rects: ...   # x0/x1/top/bottom of each box
        for l in page.lines: ...   # internal digit-cell dividers

## Fonts

All font choices are named constants in the FONTS block below — change
FONT_NAME/size there rather than hunting through drawing calls.
"""

from __future__ import annotations

import io
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.models import AtcCode, Certificate, CertificateTransaction, Transaction

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "bir2307_official_template.pdf"
PAGE_HEIGHT = 936.0  # template page is 612 x 936 pt

# --------------------------------------------------------------------------
# FONTS — the one place to change typeface/size.
# --------------------------------------------------------------------------
FONT_NAME = "Helvetica"
FONT_NAME_BOLD = "Helvetica-Bold"
FONT_SIZE_DIGITS = 10  # TIN / date per-digit boxes
FONT_SIZE_FIELD = 10  # Name / Address / Zip free-text lines
FONT_SIZE_TABLE = 8.5  # Part III line-item rows
FONT_SIZE_TABLE_BOLD = 9  # Part III totals row

# --------------------------------------------------------------------------
# Vertical centering: a "box" is (top, bottom) in pdfplumber's top-down
# measure. `nudge` is the distance from the box's top edge down to the
# text baseline, chosen so a glyph of the given font size sits visually
# centered between the box's top and bottom rule (cap-height above
# baseline, descender below) — see module docstring for how these were
# derived. Reuse the matching nudge whenever you change a font size.
# --------------------------------------------------------------------------
NUDGE_DIGITS = 10.5
NUDGE_FIELD = 11.0
NUDGE_TABLE_ROW = 9.0


def _y(top: float, nudge: float) -> float:
    """pdfplumber "top" -> reportlab bottom-up y, at a text baseline."""
    return PAGE_HEIGHT - top - nudge


# --------------------------------------------------------------------------
# Period covered — two 8-digit MM/DD/YYYY boxes, 4+4 digit cells each.
# --------------------------------------------------------------------------
PERIOD_FROM_BOX_TOP = 106.4
PERIOD_FROM_CELL_CENTERS = [157.95, 171.1, 184.7, 197.85, 210.55, 223.7, 237.3, 250.5]
PERIOD_TO_BOX_TOP = 105.7
PERIOD_TO_CELL_CENTERS = [405.55, 418.7, 432.3, 445.5, 458.25, 471.4, 485.0, 498.15]

# --------------------------------------------------------------------------
# TIN boxes — 3+3+3+5 digit cells (dashes are pre-printed by the template;
# do not draw them ourselves).
# --------------------------------------------------------------------------
PAYEE_TIN_BOX_TOP = 137.3
PAYEE_TIN_CELL_CENTERS = [
    213.25,
    226.0,
    239.75,  # first 3
    264.9,
    277.65,
    291.25,  # second 3
    316.5,
    329.45,
    342.8,  # third 3
    368.7,
    383.45,
    399.0,
    414.45,
    428.65,  # branch code, up to 5
]
PAYOR_TIN_BOX_TOP = 252.5
PAYOR_TIN_CELL_CENTERS = [
    213.85,
    226.35,
    240.3,
    265.55,
    278.3,
    292.05,
    317.2,
    330.2,
    343.7,
    369.5,
    384.25,
    399.8,
    415.25,
    429.5,
]

# --------------------------------------------------------------------------
# Name / Address / Zip — open blank-line boxes (left-aligned free text).
# --------------------------------------------------------------------------
PAYEE_NAME_BOX = (164.3, 33.9 + 4, 592.3)  # top, left, right
PAYEE_ADDRESS_BOX = (192.7, 34.5 + 4, 536.3)  # right stops short of the zip box
PAYEE_ZIP_CELL_CENTERS = [547.85, 560.6, 573.9, 586.15]

PAYOR_NAME_BOX = (279.5, 33.9 + 4, 592.3)
PAYOR_ADDRESS_BOX = (307.9, 34.5 + 4, 536.3)
PAYOR_ZIP_CELL_CENTERS = [547.85, 560.6, 573.9, 586.15]  # same row shape as payee's

# --------------------------------------------------------------------------
# Part III table — real gridline pitch is ~13.7pt; 10 line-item rows fit
# before the pre-printed "Total" row.
# --------------------------------------------------------------------------
TABLE_FIRST_ROW_TOP = 365.8
TABLE_LAST_ROW_TOP = 488.0
ROW_HEIGHT = 13.7
PART3_TOTAL_ROW_TOP = 501.7

COL_DESCRIPTION_LEFT = 19.4 + 4
COL_DESCRIPTION_WIDTH = 177.0 - 4 - COL_DESCRIPTION_LEFT
COL_ATC_CENTER = (177.0 + 220.6) / 2
COL_MONTH1_RIGHT = 291.6 - 4
COL_MONTH2_RIGHT = 365.9 - 4
COL_MONTH3_RIGHT = 438.0 - 4
COL_TOTAL_RIGHT = 510.9 - 4
COL_TAX_RIGHT = 596.0 - 4

# Short, print-friendly label per ATC code for the narrow description
# column (~157pt wide at FONT_SIZE_TABLE, room for ~30 characters) — the
# full official wording lives in atc_codes.description (see
# app/core/db.py SEED_ATC_CODES) for use anywhere else that needs it.
# Add an entry here for any new ATC code; codes without one fall back to
# a hard truncation of the full description.
SHORT_DESCRIPTIONS: dict[str, str] = {
    "WI100": "Rentals",
    "WC100": "Rentals",
    "WC120": "Contractors",
    "WC158": "Suppliers of goods",
    "WI160": "Suppliers of services",
    "WC160": "Suppliers of services",
    "WI050": "Management/tech consultants (≤₱3M)",
    "WI051": "Management/tech consultants (>₱3M)",
}


def _draw_digits(
    c: canvas.Canvas, text: str, cell_centers: list[float], y: float, font_size: float
) -> None:
    """Draw each character of `text` centered in its own box, left to right."""
    c.setFont(FONT_NAME, font_size)
    for ch, x in zip(text, cell_centers):
        c.drawCentredString(x, y, ch)


def _peso(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _fit_text(text: str, max_width: float, font: str, size: float) -> str:
    """Truncate `text` (with a trailing "...") so it renders within
    `max_width` points — measured by actual glyph width, not a guessed
    character count. Real payee/payor names and addresses are long,
    all-caps free text of wildly varying width, so a fixed character
    limit either wastes space or (as happened here) overflows into the
    next box.
    """
    if stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "..."
    ellipsis_width = stringWidth(ellipsis, font, size)
    truncated = text
    while truncated and stringWidth(truncated, font, size) + ellipsis_width > max_width:
        truncated = truncated[:-1]
    return truncated.rstrip() + ellipsis


def generate_certificate_pdf(session: Session, certificate: Certificate, output_dir: Path) -> Path:
    """Overlay `certificate`'s data onto the official template and save it.

    Transactions are grouped by ATC code (one row per code — spec's
    "multiple ATC line items per certificate", generated dynamically, not
    a fixed number of slots) and each transaction's gross amount is
    bucketed into its quarter month from `date_accomplished`, falling
    back to the period's first month when a transaction has no recorded
    date (the confirmed column mapping has no separate "date paid" field).
    """
    payee = certificate.payee
    payor = certificate.payor
    transactions = (
        session.query(Transaction)
        .join(CertificateTransaction, CertificateTransaction.transaction_id == Transaction.id)
        .filter(CertificateTransaction.certificate_id == certificate.id)
        .all()
    )

    by_atc: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        by_atc[t.atc_code].append(t)
    atc_descriptions = {a.code: a.description for a in session.query(AtcCode).all()}

    overlay_buffer = io.BytesIO()
    c = canvas.Canvas(overlay_buffer, pagesize=(letter[0], PAGE_HEIGHT))

    _draw_digits(
        c,
        certificate.period_start.strftime("%m%d%Y"),
        PERIOD_FROM_CELL_CENTERS,
        _y(PERIOD_FROM_BOX_TOP, NUDGE_DIGITS),
        FONT_SIZE_DIGITS,
    )
    _draw_digits(
        c,
        certificate.period_end.strftime("%m%d%Y"),
        PERIOD_TO_CELL_CENTERS,
        _y(PERIOD_TO_BOX_TOP, NUDGE_DIGITS),
        FONT_SIZE_DIGITS,
    )

    _draw_digits(
        c,
        payee.tin.replace("-", ""),
        PAYEE_TIN_CELL_CENTERS,
        _y(PAYEE_TIN_BOX_TOP, NUDGE_DIGITS),
        FONT_SIZE_DIGITS,
    )
    _draw_digits(
        c,
        payor.tin.replace("-", ""),
        PAYOR_TIN_CELL_CENTERS,
        _y(PAYOR_TIN_BOX_TOP, NUDGE_DIGITS),
        FONT_SIZE_DIGITS,
    )

    c.setFont(FONT_NAME, FONT_SIZE_FIELD)
    name_y = lambda top: _y(top, NUDGE_FIELD)  # noqa: E731
    name_width = PAYEE_NAME_BOX[2] - PAYEE_NAME_BOX[1]
    address_width = PAYEE_ADDRESS_BOX[2] - PAYEE_ADDRESS_BOX[1]
    c.drawString(
        PAYEE_NAME_BOX[1],
        name_y(PAYEE_NAME_BOX[0]),
        _fit_text(payee.registered_name, name_width, FONT_NAME, FONT_SIZE_FIELD),
    )
    c.drawString(
        PAYEE_ADDRESS_BOX[1],
        name_y(PAYEE_ADDRESS_BOX[0]),
        _fit_text(payee.address or "", address_width, FONT_NAME, FONT_SIZE_FIELD),
    )
    if payee.zip_code:
        _draw_digits(
            c,
            payee.zip_code,
            PAYEE_ZIP_CELL_CENTERS,
            _y(PAYEE_ADDRESS_BOX[0], NUDGE_DIGITS),
            FONT_SIZE_DIGITS,
        )

    c.setFont(FONT_NAME, FONT_SIZE_FIELD)
    payor_name_width = PAYOR_NAME_BOX[2] - PAYOR_NAME_BOX[1]
    payor_address_width = PAYOR_ADDRESS_BOX[2] - PAYOR_ADDRESS_BOX[1]
    c.drawString(
        PAYOR_NAME_BOX[1],
        name_y(PAYOR_NAME_BOX[0]),
        _fit_text(payor.registered_name, payor_name_width, FONT_NAME, FONT_SIZE_FIELD),
    )
    c.drawString(
        PAYOR_ADDRESS_BOX[1],
        name_y(PAYOR_ADDRESS_BOX[0]),
        _fit_text(payor.address or "", payor_address_width, FONT_NAME, FONT_SIZE_FIELD),
    )
    if payor.zip_code:
        _draw_digits(
            c,
            payor.zip_code,
            PAYOR_ZIP_CELL_CENTERS,
            _y(PAYOR_ADDRESS_BOX[0], NUDGE_DIGITS),
            FONT_SIZE_DIGITS,
        )

    total_amount = Decimal("0")
    total_tax = Decimal("0")
    row_top = TABLE_FIRST_ROW_TOP
    for atc_code, txs in sorted(by_atc.items()):
        month_amounts = [Decimal("0"), Decimal("0"), Decimal("0")]
        tax_for_code = Decimal("0")
        for t in txs:
            month_idx = _month_index_in_quarter(t.date_accomplished, certificate.period_start)
            month_amounts[month_idx] += t.gross_amount
            tax_for_code += t.tax_withheld
        row_total = sum(month_amounts, Decimal("0"))
        total_amount += row_total
        total_tax += tax_for_code

        y = _y(min(row_top, TABLE_LAST_ROW_TOP), NUDGE_TABLE_ROW)
        c.setFont(FONT_NAME, FONT_SIZE_TABLE)
        description = SHORT_DESCRIPTIONS.get(atc_code) or _fit_text(
            atc_descriptions.get(atc_code) or "", COL_DESCRIPTION_WIDTH, FONT_NAME, FONT_SIZE_TABLE
        )
        c.drawString(COL_DESCRIPTION_LEFT, y, description)
        c.drawCentredString(COL_ATC_CENTER, y, atc_code)
        c.drawRightString(COL_MONTH1_RIGHT, y, _peso(month_amounts[0]) if month_amounts[0] else "")
        c.drawRightString(COL_MONTH2_RIGHT, y, _peso(month_amounts[1]) if month_amounts[1] else "")
        c.drawRightString(COL_MONTH3_RIGHT, y, _peso(month_amounts[2]) if month_amounts[2] else "")
        c.drawRightString(COL_TOTAL_RIGHT, y, _peso(row_total))
        c.drawRightString(COL_TAX_RIGHT, y, _peso(tax_for_code))
        row_top += ROW_HEIGHT

    c.setFont(FONT_NAME_BOLD, FONT_SIZE_TABLE_BOLD)
    total_y = _y(PART3_TOTAL_ROW_TOP, NUDGE_TABLE_ROW)
    c.drawRightString(COL_TOTAL_RIGHT, total_y, _peso(total_amount))
    c.drawRightString(COL_TAX_RIGHT, total_y, _peso(total_tax))

    c.save()
    overlay_buffer.seek(0)

    template_reader = PdfReader(str(TEMPLATE_PATH))
    overlay_reader = PdfReader(overlay_buffer)
    base_page = template_reader.pages[0]
    base_page.merge_page(overlay_reader.pages[0])

    writer = PdfWriter()
    writer.add_page(base_page)

    payee_tin_dir = output_dir / payee.tin.replace("/", "-")
    payee_tin_dir.mkdir(parents=True, exist_ok=True)
    out_path = payee_tin_dir / f"{certificate.id}_unsigned.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)

    certificate.pdf_unsigned_path = str(out_path)
    return out_path


def _month_index_in_quarter(date_accomplished, period_start) -> int:
    if date_accomplished is None:
        return 0
    offset = date_accomplished.month - period_start.month
    return offset if 0 <= offset <= 2 else 0
