"""Payee/payor record editing.

The MVP had no way to correct a record after import short of a direct DB
edit (see README's placeholder-payor fix) — this is the one write path for
`payees`/`payors` outside of the Excel importer. Every edit is logged to
`event_logs` (category SYSTEM, unused elsewhere) with the before/after
values in `technical_detail` so a correction is traceable, matching the
audit intent already applied to certificate status changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.computation import compute_amount_paid, compute_tax_base, compute_tax_withheld
from app.core.logging_config import log_event
from app.core.models import AtcCode, EventCategory, EventSeverity, Payee, Payor, TaxType, Transaction
from app.core.security import is_valid_tin, normalize_tin, sanitize_text
from app.core.text_match import contains_ci, normalize_tin_digits


class DuplicateTinError(ValueError):
    """Raised when a payee edit's TIN would collide with a different payee."""


class UnknownAtcCodeError(ValueError):
    """Raised when a transaction edit's ATC code isn't in the rate table."""


@dataclass(frozen=True)
class PayorFields:
    tin: str
    registered_name: str
    address: str | None
    zip_code: str | None


@dataclass(frozen=True)
class PayeeFields:
    tin: str
    registered_name: str
    address: str | None
    zip_code: str | None
    tax_type: TaxType


def _diff(before: dict[str, str | None], after: dict[str, str | None]) -> str:
    changed = {k: (before[k], after[k]) for k in after if before.get(k) != after[k]}
    return "; ".join(f"{k}: {old!r} -> {new!r}" for k, (old, new) in changed.items())


def search_payees(
    session: Session, *, name: str | None = None, tin: str | None = None
) -> list[Payee]:
    """Combinable name-substring / digits-only-TIN-substring filter over payees,
    matching the search behavior already used for certificates in core/search.py."""
    candidates = session.query(Payee).order_by(Payee.registered_name).all()

    def matches(payee: Payee) -> bool:
        if not contains_ci(payee.registered_name, name):
            return False
        if tin and tin.strip() and normalize_tin_digits(tin) not in normalize_tin_digits(payee.tin):
            return False
        return True

    return [p for p in candidates if matches(p)]


def update_payor(
    session: Session, payor: Payor, fields: PayorFields, changed_by: str
) -> Payor:
    """Overwrite `payor`'s fields, logging a diff. Never blocks on a malformed TIN."""
    before = {
        "tin": payor.tin,
        "registered_name": payor.registered_name,
        "address": payor.address,
        "zip_code": payor.zip_code,
    }
    tin = normalize_tin(fields.tin)
    after = {
        "tin": tin,
        "registered_name": sanitize_text(fields.registered_name)
        or fields.registered_name,
        "address": sanitize_text(fields.address),
        "zip_code": sanitize_text(fields.zip_code),
    }

    payor.tin = after["tin"]
    payor.registered_name = after["registered_name"]
    payor.address = after["address"]
    payor.zip_code = after["zip_code"]

    diff = _diff(before, after)
    if diff:
        log_event(
            session,
            category=EventCategory.SYSTEM,
            severity=EventSeverity.INFO,
            message=f"Payor #{payor.id} record updated by {changed_by}.",
            technical_detail=diff,
        )
    if not is_valid_tin(tin):
        log_event(
            session,
            category=EventCategory.TIN_FORMAT,
            severity=EventSeverity.WARNING,
            message=f"Payor #{payor.id} TIN does not match the expected ###-###-###-### format.",
            technical_detail=f"tin={tin!r}",
        )
    return payor


def update_payee(
    session: Session, payee: Payee, fields: PayeeFields, changed_by: str
) -> Payee:
    """Overwrite `payee`'s fields, logging a diff. Raises DuplicateTinError if the
    new TIN already belongs to a different payee; never blocks on a malformed TIN."""
    tin = normalize_tin(fields.tin)
    if tin != payee.tin:
        collision = (
            session.query(Payee).filter(Payee.tin == tin, Payee.id != payee.id).first()
        )
        if collision is not None:
            raise DuplicateTinError(
                f"TIN {tin} already belongs to payee #{collision.id} ({collision.registered_name})."
            )

    before = {
        "tin": payee.tin,
        "registered_name": payee.registered_name,
        "address": payee.address,
        "zip_code": payee.zip_code,
        "tax_type": payee.tax_type.value,
    }
    after = {
        "tin": tin,
        "registered_name": sanitize_text(fields.registered_name)
        or fields.registered_name,
        "address": sanitize_text(fields.address),
        "zip_code": sanitize_text(fields.zip_code),
        "tax_type": fields.tax_type.value,
    }

    payee.tin = after["tin"]
    payee.registered_name = after["registered_name"]
    payee.address = after["address"]
    payee.zip_code = after["zip_code"]
    payee.tax_type = fields.tax_type

    diff = _diff(before, after)
    if diff:
        log_event(
            session,
            category=EventCategory.SYSTEM,
            severity=EventSeverity.INFO,
            message=f"Payee #{payee.id} record updated by {changed_by}.",
            technical_detail=diff,
        )
    if not is_valid_tin(tin):
        log_event(
            session,
            category=EventCategory.TIN_FORMAT,
            severity=EventSeverity.WARNING,
            message=f"Payee #{payee.id} TIN does not match the expected ###-###-###-### format.",
            technical_detail=f"tin={tin!r}",
        )
    return payee


@dataclass(frozen=True)
class TransactionFields:
    reference_no: str
    atc_code: str
    gross_amount: Decimal
    total_billing: Decimal
    invoice_date: datetime | None


def update_transaction(
    session: Session, transaction: Transaction, fields: TransactionFields, changed_by: str
) -> Transaction:
    """Overwrite `transaction`'s editable fields, recomputing tax_base/
    tax_withheld/amount_paid the exact same way the importer does (see
    `app/core/computation.py`) so an edited transaction stays internally
    consistent instead of drifting from what a fresh import would produce.
    Raises UnknownAtcCodeError if `fields.atc_code` isn't in the rate
    table. Caller is responsible for recomputing any certificate totals
    and regenerating its PDF afterward — this only touches the row.
    """
    atc = session.get(AtcCode, fields.atc_code)
    if atc is None:
        raise UnknownAtcCodeError(f'ATC code "{fields.atc_code}" is not in the rate table.')

    before = {
        "reference_no": transaction.reference_no,
        "atc_code": transaction.atc_code,
        "gross_amount": str(transaction.gross_amount),
        "total_billing": str(transaction.total_billing),
        "tax_withheld": str(transaction.tax_withheld),
        "invoice_date": transaction.invoice_date.isoformat() if transaction.invoice_date else None,
    }

    tax_base = compute_tax_base(fields.gross_amount, transaction.payee.tax_type.value)
    tax_withheld = compute_tax_withheld(tax_base, atc.default_rate)
    amount_paid = compute_amount_paid(fields.total_billing, tax_withheld)

    transaction.reference_no = sanitize_text(fields.reference_no) or fields.reference_no
    transaction.atc_code = fields.atc_code
    transaction.gross_amount = fields.gross_amount
    transaction.total_billing = fields.total_billing
    transaction.tax_base = tax_base
    transaction.rate_applied = atc.default_rate
    transaction.tax_withheld = tax_withheld
    transaction.amount_paid = amount_paid
    transaction.invoice_date = fields.invoice_date

    after = {
        "reference_no": transaction.reference_no,
        "atc_code": transaction.atc_code,
        "gross_amount": str(transaction.gross_amount),
        "total_billing": str(transaction.total_billing),
        "tax_withheld": str(transaction.tax_withheld),
        "invoice_date": transaction.invoice_date.isoformat() if transaction.invoice_date else None,
    }
    diff = _diff(before, after)
    if diff:
        log_event(
            session,
            category=EventCategory.SYSTEM,
            severity=EventSeverity.INFO,
            message=f"Transaction #{transaction.id} record updated by {changed_by}.",
            technical_detail=diff,
            transaction_id=transaction.id,
        )
    return transaction
