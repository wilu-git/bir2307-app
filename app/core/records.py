"""Payee/payor record editing.

The MVP had no way to correct a record after import short of a direct DB
edit (see README's placeholder-payor fix) — this is the one write path for
`payees`/`payors` outside of the Excel importer. Every edit is logged to
`event_logs` (category SYSTEM, unused elsewhere) with the before/after
values in `technical_detail` so a correction is traceable, matching the
audit intent already applied to certificate status changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.logging_config import log_event
from app.core.models import EventCategory, EventSeverity, Payee, Payor, TaxType
from app.core.security import is_valid_tin, normalize_tin, sanitize_text

_NON_DIGITS_RE = re.compile(r"\D+")


class DuplicateTinError(ValueError):
    """Raised when a payee edit's TIN would collide with a different payee."""


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
    email: str | None
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
    name_needle = name.strip().lower() if name and name.strip() else None
    tin_needle = _NON_DIGITS_RE.sub("", tin) if tin and tin.strip() else None

    def matches(payee: Payee) -> bool:
        if name_needle and name_needle not in payee.registered_name.lower():
            return False
        if tin_needle and tin_needle not in _NON_DIGITS_RE.sub("", payee.tin):
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
        "email": payee.email,
        "tax_type": payee.tax_type.value,
    }
    after = {
        "tin": tin,
        "registered_name": sanitize_text(fields.registered_name)
        or fields.registered_name,
        "address": sanitize_text(fields.address),
        "zip_code": sanitize_text(fields.zip_code),
        "email": sanitize_text(fields.email),
        "tax_type": fields.tax_type.value,
    }

    payee.tin = after["tin"]
    payee.registered_name = after["registered_name"]
    payee.address = after["address"]
    payee.zip_code = after["zip_code"]
    payee.email = after["email"]
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
