"""Certificate grouping: transactions -> one certificate per payee+quarter.

A "period" is the calendar quarter containing each transaction's anchor
date (`date_accomplished` if the sheet had it, else the transaction's
import timestamp — the confirmed column mapping has no dedicated
"date paid" field, so this is the best available anchor for MVP).

Grouping is idempotent and additive: re-running it after a fresh import
finds each payee+quarter's existing certificate (never creates a second
one for the same payee+period — spec's hard rule) and links any new
transactions into it, recomputing totals. It never touches the status of
an already-existing certificate — that's left to the explicit
Certificates-page status control (or the status derived from the sheet at
creation time), so a later re-import can't silently downgrade progress a
user has already recorded in-app.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.import_excel import _parse_bool_flag, derive_certificate_status
from app.core.logging_config import log_event
from app.core.models import (
    Certificate,
    CertificateStatus,
    CertificateTransaction,
    EventCategory,
    EventSeverity,
    StatusLog,
    Transaction,
)

_STATUS_RANK = {
    CertificateStatus.DRAFT: 0,
    CertificateStatus.GENERATED: 1,
    CertificateStatus.FORWARDED: 2,
    CertificateStatus.COMPLETED_SIGNED: 3,
    CertificateStatus.VOID: -1,
}


def quarter_bounds(dt: datetime) -> tuple[datetime, datetime]:
    """First/last calendar day of the quarter containing `dt`."""
    quarter_start_month = ((dt.month - 1) // 3) * 3 + 1
    start = datetime(dt.year, quarter_start_month, 1)
    if quarter_start_month == 10:
        end = datetime(dt.year, 12, 31)
    else:
        end = datetime(dt.year, quarter_start_month + 3, 1)
        end = end.replace(day=1)
        end = datetime(end.year, end.month, 1) - _one_day()
    return start, end


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _status_from_transaction(transaction: Transaction) -> CertificateStatus:
    """Re-derive the sheet's status for one transaction from its stored raw row."""
    if not transaction.raw_row_json:
        return CertificateStatus.DRAFT
    raw = json.loads(transaction.raw_row_json)
    signed = _parse_bool_flag(raw.get("signed copy google drive"))
    not_signed = _parse_bool_flag(raw.get("not signed"))
    status_text = raw.get("status")
    status, _ambiguous = derive_certificate_status(signed, not_signed, status_text)
    return status


def group_ungrouped_transactions(session: Session) -> list[Certificate]:
    """Link every not-yet-certified transaction into a payee+quarter certificate.

    Returns the set of certificates that were created or received new
    transactions in this call (for UI feedback).
    """
    linked_ids = {
        row.transaction_id for row in session.query(CertificateTransaction.transaction_id)
    }
    ungrouped = (
        session.query(Transaction).filter(~Transaction.id.in_(linked_ids)).all()
        if linked_ids
        else session.query(Transaction).all()
    )

    buckets: dict[tuple[int, datetime, datetime], list[Transaction]] = defaultdict(list)
    for transaction in ungrouped:
        anchor = transaction.date_accomplished or transaction.created_at
        period_start, period_end = quarter_bounds(anchor)
        buckets[(transaction.payee_id, period_start, period_end)].append(transaction)

    touched: list[Certificate] = []
    for (payee_id, period_start, period_end), txs in buckets.items():
        payor_id = txs[0].payor_id
        certificate = (
            session.query(Certificate)
            .filter_by(
                payee_id=payee_id,
                payor_id=payor_id,
                period_start=period_start,
                period_end=period_end,
            )
            .one_or_none()
        )
        is_new = certificate is None
        if is_new:
            certificate = Certificate(
                payee_id=payee_id,
                payor_id=payor_id,
                period_start=period_start,
                period_end=period_end,
                total_gross=0,
                total_tax_withheld=0,
                status=CertificateStatus.DRAFT,
            )
            session.add(certificate)
            session.flush()

        for transaction in txs:
            session.add(
                CertificateTransaction(certificate_id=certificate.id, transaction_id=transaction.id)
            )
        session.flush()

        _recompute_totals(session, certificate)
        if is_new:
            _set_initial_status(certificate, txs)
        touched.append(certificate)

    session.commit()
    return touched


def _recompute_totals(session: Session, certificate: Certificate) -> None:
    linked = (
        session.query(Transaction)
        .join(CertificateTransaction, CertificateTransaction.transaction_id == Transaction.id)
        .filter(CertificateTransaction.certificate_id == certificate.id)
        .all()
    )
    certificate.total_gross = sum((t.gross_amount for t in linked), Decimal("0"))
    certificate.total_tax_withheld = sum((t.tax_withheld for t in linked), Decimal("0"))


def _set_initial_status(certificate: Certificate, txs: list[Transaction]) -> None:
    best = CertificateStatus.DRAFT
    for t in txs:
        status = _status_from_transaction(t)
        if _STATUS_RANK[status] > _STATUS_RANK[best]:
            best = status
    certificate.status = best


def transition_status(
    session: Session,
    certificate: Certificate,
    new_status: CertificateStatus,
    changed_by: str,
    note: str | None = None,
) -> None:
    """Move `certificate` to `new_status`, recording an append-only
    `status_log` row and mirroring a `STATUS_TRANSITION` event log entry.

    A no-op (no log rows written) if `new_status` matches the current
    status — callers driving this from a UI control don't need to guard
    against re-submitting the unchanged value themselves.
    """
    if new_status == certificate.status:
        return
    old_status = certificate.status.value
    certificate.status = new_status
    session.add(
        StatusLog(
            certificate_id=certificate.id,
            old_status=old_status,
            new_status=new_status.value,
            changed_by=changed_by,
            note=note,
        )
    )
    log_event(
        session,
        category=EventCategory.STATUS_TRANSITION,
        severity=EventSeverity.INFO,
        message=f"Certificate #{certificate.id} status changed {old_status} -> {new_status.value}.",
        technical_detail=f"changed_by={changed_by} note={note!r}",
        certificate_id=certificate.id,
    )
