"""Excel ingest: column mapping, validation, dedup detection, EWT recompute.

Targets the sheet literally named "BIR 2307" inside the source workbook by
default (the real Favor Church export is a 16-sheet workbook where that's
one sheet among many unrelated ones — payroll, budget, donations, etc.).

Row parsing is a pure function (`parse_row`) so it's unit-testable without a
database. The orchestrator (`import_workbook`) wraps each row in a
try/except so one bad row never aborts the batch, and does all DB writes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy.orm import Session

from app.core.computation import (
    compute_amount_paid,
    compute_tax_base,
    compute_tax_withheld,
    is_mismatch,
)
from app.core.logging_config import log_event
from app.core.models import (
    AtcCode,
    CertificateStatus,
    EventCategory,
    EventSeverity,
    ImportBatch,
    Payee,
    Payor,
    TaxType,
    Transaction,
)
from app.core.security import is_valid_tin, normalize_tin, sanitize_text

DEFAULT_SHEET_NAME = "BIR 2307"

# Normalized-header -> internal field name. Headers are normalized (see
# normalize_header) before lookup so embedded newlines in the real workbook
# (e.g. "Signed Copy \nGoogle Drive") still match.
COLUMN_MAP: dict[str, str] = {
    "signed copy google drive": "signed_flag",
    "not signed": "not_signed_flag",
    "corporate email address": "email",
    "bill no.": "reference_no",
    "corporate name": "registered_name",
    "corporate address": "address",
    "zip code": "zip_code",
    "tin number": "tin",
    "tax code": "atc_code",
    "vat / nonvat": "tax_type",
    "total billing": "total_billing",
    "gross amount": "gross_amount",
    "amount paid": "uploaded_amount_paid",
    "amount at 2307": "uploaded_tax_base",
    "tax withheld": "uploaded_tax_withheld",
    "status": "status_text",
    "assigned to": "assigned_to",
    "date accomplished": "date_accomplished",
    "remarks": "remarks",
}
OVERFLOW_PREFIX = "column "  # "Column 1".."Column 16" -> overflow_notes
EXCLUDED_HEADERS = {"a", "column 39", "file name", "not subject to ewt"}

# Fields `parse_row` cannot proceed without — a column-mapping UI must have
# all four assigned to some source header before an import can run.
MANDATORY_FIELDS = {"reference_no", "tin", "gross_amount", "atc_code"}


def normalize_header(header: object) -> str:
    """Collapse whitespace/newlines and lowercase for robust header matching."""
    return " ".join(str(header).split()).lower()


@dataclass
class ParsedRow:
    row_number: int  # 1-based, matches spreadsheet row (header = row 1)
    reference_no: str
    tin: str
    registered_name: str
    address: str | None
    zip_code: str | None
    email: str | None
    tax_type: str
    atc_code: str
    total_billing: Decimal
    gross_amount: Decimal
    uploaded_tax_base: Decimal | None
    uploaded_amount_paid: Decimal | None
    uploaded_tax_withheld: Decimal | None
    assigned_to: str | None
    date_accomplished: datetime | None
    remarks: str | None
    overflow_notes: str | None
    signed_flag: bool
    not_signed_flag: bool
    status_text: str | None
    raw_row: dict = field(default_factory=dict)


class RowParseError(ValueError):
    """Raised for a single unparseable row; caller must catch and continue."""


def _clean_str(value: object) -> str:
    """String-ify a raw cell, collapsing pandas NaN/None to "" instead of
    the literal text "nan" (float("nan") is truthy, so a bare `value or ""`
    silently lets missing numeric-typed cells through as the string "nan")."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _parse_decimal(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_bool_flag(value: object) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "x"}


def _parse_date(value: object) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    text = str(value).strip()
    if not text:
        return None
    try:
        serial = float(text)
        # Excel's day-0 epoch is 1899-12-30 (accounts for the historical leap-year bug).
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=serial)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _read_normalized_dataframe(file, sheet_name: str) -> pd.DataFrame:
    """Read `sheet_name` and normalize its column headers. Shared by
    `read_source_rows` and `detect_headers` so both see the same headers."""
    df = pd.read_excel(file, sheet_name=sheet_name, header=0, dtype=object)
    df.columns = [normalize_header(c) for c in df.columns]
    return df


def detect_headers(file, sheet_name: str = DEFAULT_SHEET_NAME) -> list[str]:
    """Normalized header names found in `sheet_name`, in sheet order — used
    by the column-mapping UI to show what's actually in the uploaded file."""
    df = _read_normalized_dataframe(file, sheet_name)
    return list(df.columns)


def read_source_rows(
    file, sheet_name: str = DEFAULT_SHEET_NAME, column_map: dict[str, str] = COLUMN_MAP
) -> list[dict]:
    """Read `sheet_name` from the uploaded workbook, normalizing headers.

    `file` is anything pandas.read_excel accepts (path or file-like buffer).
    Returns a list of raw dicts keyed by normalized header, one per data
    row. Values are kept as pandas gave them (str/float/Timestamp/NaN) —
    conversion happens in `parse_row`.

    Structural non-transaction rows are silently dropped here rather than
    surfaced as ROW_VALIDATION errors later: the real sheet has periodic
    "TOTAL AMOUNT" subtotal rows and trailing blank template rows, and
    because "Column 39"/"FILE NAME" auto-populate on every row (even blank
    ones), a naive all-cells-empty check doesn't catch them. A row missing
    both the column mapped to `reference_no` and the column mapped to `tin`
    can't be a real transaction — nothing in this app can attribute it to a
    payee — so it's dropped before parsing instead of being logged as a
    scary error for a non-technical user to triage. Which source columns
    those are is resolved from `column_map` (not hardcoded to "bill no."/
    "tin number") so a remapped upload's blank-row filter stays in sync
    with wherever the user pointed those two fields.
    """
    df = _read_normalized_dataframe(file, sheet_name)

    reference_header = next((h for h, f in column_map.items() if f == "reference_no"), None)
    tin_header = next((h for h, f in column_map.items() if f == "tin"), None)

    def _is_blank(value: object) -> bool:
        return (
            value is None
            or (isinstance(value, float) and pd.isna(value))
            or str(value).strip() == ""
        )

    rows: list[dict] = []
    for _, series in df.iterrows():
        row = series.to_dict()
        reference_blank = reference_header is None or _is_blank(row.get(reference_header))
        tin_blank = tin_header is None or _is_blank(row.get(tin_header))
        if reference_blank and tin_blank:
            continue
        rows.append(row)
    return rows


def parse_row(
    raw_row: dict, row_number: int, column_map: dict[str, str] = COLUMN_MAP
) -> ParsedRow:
    """Map one raw spreadsheet row to a ParsedRow. Raises RowParseError on
    missing required fields (reference_no, tin, gross_amount, atc_code)."""
    mapped: dict[str, object] = {}
    overflow_parts: list[str] = []
    for header, value in raw_row.items():
        if header in EXCLUDED_HEADERS:
            continue
        if header.startswith(OVERFLOW_PREFIX):
            if value is not None and not (isinstance(value, float) and pd.isna(value)):
                text = str(value).strip()
                if text:
                    overflow_parts.append(text)
            continue
        field_name = column_map.get(header)
        if field_name:
            mapped[field_name] = value

    reference_no = sanitize_text(_clean_str(mapped.get("reference_no")))
    tin_raw = _clean_str(mapped.get("tin"))
    gross_amount = _parse_decimal(mapped.get("gross_amount"))
    atc_code = _clean_str(mapped.get("atc_code")).upper()

    if not reference_no:
        raise RowParseError(f"Row {row_number}: missing BILL NO.")
    if not tin_raw:
        raise RowParseError(f"Row {row_number}: missing TIN NUMBER")
    if gross_amount is None:
        raise RowParseError(f"Row {row_number}: missing/invalid GROSS AMOUNT")
    if not atc_code:
        raise RowParseError(f"Row {row_number}: missing TAX CODE")

    tax_type = "VAT" if _clean_str(mapped.get("tax_type")).upper() == "VAT" else "NONVAT"

    total_billing = _parse_decimal(mapped.get("total_billing"))
    if total_billing is None:
        total_billing = gross_amount

    registered_name = sanitize_text(_clean_str(mapped.get("registered_name"))) or "UNKNOWN"

    return ParsedRow(
        row_number=row_number,
        reference_no=reference_no,
        tin=normalize_tin(tin_raw),
        registered_name=registered_name,
        address=sanitize_text(_clean_str(mapped.get("address"))) or None,
        zip_code=sanitize_text(_clean_str(mapped.get("zip_code"))) or None,
        email=sanitize_text(_clean_str(mapped.get("email"))) or None,
        tax_type=tax_type,
        atc_code=atc_code,
        total_billing=total_billing,
        gross_amount=gross_amount,
        uploaded_tax_base=_parse_decimal(mapped.get("uploaded_tax_base")),
        uploaded_amount_paid=_parse_decimal(mapped.get("uploaded_amount_paid")),
        uploaded_tax_withheld=_parse_decimal(mapped.get("uploaded_tax_withheld")),
        assigned_to=sanitize_text(_clean_str(mapped.get("assigned_to"))) or None,
        date_accomplished=_parse_date(mapped.get("date_accomplished")),
        remarks=sanitize_text(_clean_str(mapped.get("remarks"))) or None,
        overflow_notes="; ".join(overflow_parts) or None,
        signed_flag=_parse_bool_flag(mapped.get("signed_flag")),
        not_signed_flag=_parse_bool_flag(mapped.get("not_signed_flag")),
        status_text=sanitize_text(_clean_str(mapped.get("status_text"))) or None,
        raw_row={
            k: (None if isinstance(v, float) and pd.isna(v) else str(v)) for k, v in raw_row.items()
        },
    )


def derive_certificate_status(
    signed_flag: bool, not_signed_flag: bool, status_text: str | None
) -> tuple[CertificateStatus, bool]:
    """Collapse the two boolean flags + free-text Status into one enum.

    Returns (status, is_ambiguous). Ambiguous cases (both flags true, or
    both false with no recognizable status text) default to DRAFT per spec
    and are reported back to the caller so it can log a ROW_VALIDATION
    warning — this function itself never logs, so it's testable in isolation.
    """
    text = (status_text or "").lower()

    if signed_flag and not_signed_flag:
        return CertificateStatus.DRAFT, True

    if signed_flag:
        return CertificateStatus.COMPLETED_SIGNED, False

    if not_signed_flag:
        if "forward" in text or "submit" in text:
            return CertificateStatus.FORWARDED, False
        if "not started" in text:
            return CertificateStatus.DRAFT, False
        if not text:
            return CertificateStatus.DRAFT, True  # no clear status text
        return CertificateStatus.FORWARDED, False

    # Neither flag set.
    if "complet" in text or "signed" in text:
        return CertificateStatus.COMPLETED_SIGNED, False
    if "forward" in text or "submit" in text:
        return CertificateStatus.FORWARDED, False
    if "not started" in text:
        return CertificateStatus.DRAFT, False
    return CertificateStatus.DRAFT, True  # no clear status text either way


@dataclass
class DuplicateGroup:
    key: tuple[str, str]
    indices: list[int]
    is_accidental_duplicate: bool  # True = collapse to one; False = legitimate merge


def find_duplicate_groups(rows: list[ParsedRow]) -> list[DuplicateGroup]:
    """Group rows sharing (reference_no, tin); classify each group.

    Identical GROSS AMOUNT + TAX WITHHELD + Date Accomplished across the
    group -> accidental duplicate entry (collapse to one transaction).
    Any difference -> legitimate multi-row billing for the same reference
    (merge into one certificate later, keep as separate transactions).
    """
    by_key: dict[tuple[str, str], list[int]] = {}
    for i, row in enumerate(rows):
        by_key.setdefault((row.reference_no, row.tin), []).append(i)

    groups: list[DuplicateGroup] = []
    for key, indices in by_key.items():
        if len(indices) < 2:
            continue
        signatures = {
            (rows[i].gross_amount, rows[i].uploaded_tax_withheld, rows[i].date_accomplished)
            for i in indices
        }
        groups.append(
            DuplicateGroup(key=key, indices=indices, is_accidental_duplicate=len(signatures) == 1)
        )
    return groups


def _get_or_create_payee(session: Session, row: ParsedRow) -> Payee:
    payee = session.query(Payee).filter_by(tin=row.tin).one_or_none()
    tax_type_enum = TaxType.VAT if row.tax_type == "VAT" else TaxType.NONVAT
    if payee is None:
        payee = Payee(
            tin=row.tin,
            registered_name=row.registered_name,
            address=row.address,
            zip_code=row.zip_code,
            email=row.email,
            tax_type=tax_type_enum,
        )
        session.add(payee)
        session.flush()
    else:
        payee.registered_name = row.registered_name or payee.registered_name
        payee.address = row.address or payee.address
        payee.zip_code = row.zip_code or payee.zip_code
        payee.email = row.email or payee.email
        payee.tax_type = tax_type_enum
    return payee


def import_workbook(
    session: Session,
    file,
    filename: str,
    uploaded_by: str,
    sheet_name: str = DEFAULT_SHEET_NAME,
    column_map: dict[str, str] = COLUMN_MAP,
) -> ImportBatch:
    """Full ingest pipeline: parse -> dedup-classify -> recompute -> persist.

    Never raises on a single bad row (logged and skipped instead); the only
    exceptions that propagate are ones that mean the file itself can't be
    read at all (wrong sheet name, corrupt workbook), logged as FILE_PARSE.

    `column_map` defaults to the module-level `COLUMN_MAP` so unmodified
    callers (demo seeding, tests) behave exactly as before; pass a
    different mapping (see `core/mapping_profiles.py`) for a spreadsheet
    whose columns don't match that default.
    """
    payor = session.query(Payor).first()
    if payor is None:
        raise RuntimeError("No payor configured — run init_db() first.")

    batch = ImportBatch(filename=filename, uploaded_by=uploaded_by, row_count=0)
    session.add(batch)
    session.flush()

    try:
        raw_rows = read_source_rows(file, sheet_name=sheet_name, column_map=column_map)
    except Exception as exc:  # file-level failure: nothing to import
        log_event(
            session,
            category=EventCategory.FILE_PARSE,
            severity=EventSeverity.ERROR,
            message=f'Could not read sheet "{sheet_name}" from {filename}.',
            technical_detail=repr(exc),
            batch_id=batch.id,
        )
        session.commit()
        return batch

    batch.row_count = len(raw_rows)

    parsed_rows: list[ParsedRow] = []
    for idx, raw in enumerate(raw_rows):
        row_number = idx + 2  # +1 for 0-index, +1 for header row
        try:
            parsed_rows.append(parse_row(raw, row_number, column_map=column_map))
        except RowParseError as exc:
            batch.error_count += 1
            log_event(
                session,
                category=EventCategory.ROW_VALIDATION,
                severity=EventSeverity.ERROR,
                message=str(exc),
                technical_detail=json.dumps(raw, default=str),
                batch_id=batch.id,
            )
        except Exception as exc:  # defensive: never let one row abort the batch
            batch.error_count += 1
            log_event(
                session,
                category=EventCategory.ROW_VALIDATION,
                severity=EventSeverity.ERROR,
                message=f"Row {row_number}: unexpected error while parsing.",
                technical_detail=repr(exc),
                batch_id=batch.id,
            )

    skip_indices: set[int] = set()
    for group in find_duplicate_groups(parsed_rows):
        rows_in_group = [parsed_rows[i] for i in group.indices]
        if group.is_accidental_duplicate:
            keep_idx, *drop_idx = group.indices
            skip_indices.update(drop_idx)
            log_event(
                session,
                category=EventCategory.DUPLICATE_REFERENCE,
                severity=EventSeverity.WARNING,
                message=(
                    f'BILL NO. "{group.key[0]}" repeated {len(group.indices)} times with '
                    "identical amounts/date for the same payee — treated as accidental "
                    "duplicate entry; only one transaction was imported."
                ),
                technical_detail=json.dumps([r.raw_row for r in rows_in_group], default=str),
                batch_id=batch.id,
            )
        else:
            log_event(
                session,
                category=EventCategory.DUPLICATE_REFERENCE,
                severity=EventSeverity.INFO,
                message=(
                    f'BILL NO. "{group.key[0]}" appears {len(group.indices)} times with '
                    "differing amounts/date for the same payee — importing as separate "
                    "transactions to be merged into one certificate."
                ),
                technical_detail=json.dumps([r.raw_row for r in rows_in_group], default=str),
                batch_id=batch.id,
            )

    for i, row in enumerate(parsed_rows):
        if i in skip_indices:
            continue
        try:
            _import_single_row(session, batch, payor, row)
            batch.success_count += 1
        except Exception as exc:
            batch.error_count += 1
            log_event(
                session,
                category=EventCategory.ROW_VALIDATION,
                severity=EventSeverity.ERROR,
                message=f"Row {row.row_number}: failed to import.",
                technical_detail=repr(exc),
                batch_id=batch.id,
            )

    session.commit()
    return batch


def _import_single_row(session: Session, batch: ImportBatch, payor: Payor, row: ParsedRow) -> None:
    if not is_valid_tin(row.tin):
        log_event(
            session,
            category=EventCategory.TIN_FORMAT,
            severity=EventSeverity.WARNING,
            message=f'Row {row.row_number}: TIN "{row.tin[:3]}-XXX-XXX-XXXXX" does not match the expected format.',
            technical_detail=f"raw_tin={row.tin!r}",
            batch_id=batch.id,
        )

    atc = session.get(AtcCode, row.atc_code)
    if atc is None:
        log_event(
            session,
            category=EventCategory.ATC_RATE_UNKNOWN,
            severity=EventSeverity.ERROR,
            message=(
                f'Row {row.row_number}: ATC code "{row.atc_code}" is not in the rate table — '
                "row skipped. Add it to atc_codes to import this row."
            ),
            technical_detail=json.dumps(row.raw_row, default=str),
            batch_id=batch.id,
        )
        return

    payee = _get_or_create_payee(session, row)

    tax_base = compute_tax_base(row.gross_amount, row.tax_type)
    tax_withheld = compute_tax_withheld(tax_base, atc.default_rate)
    amount_paid = compute_amount_paid(row.total_billing, tax_withheld)

    mismatches = []
    if is_mismatch(tax_base, row.uploaded_tax_base):
        mismatches.append(f"tax_base computed={tax_base} uploaded={row.uploaded_tax_base}")
    if is_mismatch(tax_withheld, row.uploaded_tax_withheld):
        mismatches.append(
            f"tax_withheld computed={tax_withheld} uploaded={row.uploaded_tax_withheld}"
        )
    if is_mismatch(amount_paid, row.uploaded_amount_paid):
        mismatches.append(f"amount_paid computed={amount_paid} uploaded={row.uploaded_amount_paid}")

    transaction = Transaction(
        batch_id=batch.id,
        payee_id=payee.id,
        payor_id=payor.id,
        reference_no=row.reference_no,
        atc_code=atc.code,
        total_billing=row.total_billing,
        gross_amount=row.gross_amount,
        tax_base=tax_base,
        rate_applied=atc.default_rate,
        tax_withheld=tax_withheld,
        amount_paid=amount_paid,
        assigned_to=row.assigned_to,
        date_accomplished=row.date_accomplished,
        remarks=row.remarks,
        overflow_notes=row.overflow_notes,
        raw_row_json=json.dumps(row.raw_row, default=str),
    )
    session.add(transaction)
    session.flush()

    if mismatches:
        log_event(
            session,
            category=EventCategory.COMPUTATION_MISMATCH,
            severity=EventSeverity.WARNING,
            message=(
                f"Row {row.row_number}: recomputed values differ from the uploaded "
                f"spreadsheet by more than ₱0.01 ({len(mismatches)} field(s))."
            ),
            technical_detail="; ".join(mismatches),
            batch_id=batch.id,
            transaction_id=transaction.id,
        )

    _, ambiguous = derive_certificate_status(row.signed_flag, row.not_signed_flag, row.status_text)
    if ambiguous:
        log_event(
            session,
            category=EventCategory.ROW_VALIDATION,
            severity=EventSeverity.WARNING,
            message=(
                f"Row {row.row_number}: signed/not-signed flags or status text are "
                "ambiguous or contradictory — defaulted to draft."
            ),
            technical_detail=(
                f"signed_flag={row.signed_flag} not_signed_flag={row.not_signed_flag} "
                f"status_text={row.status_text!r}"
            ),
            batch_id=batch.id,
            transaction_id=transaction.id,
        )
