"""Certificate grouping: transactions -> one certificate per payee+quarter.

A "period" is the calendar quarter containing each transaction's anchor
date (`invoice_date` if the sheet had it, else the transaction's import
timestamp).

Grouping is idempotent and additive: re-running it after a fresh import
finds each payee+quarter's existing certificate (never creates a second
one for the same payee+period — spec's hard rule) and links any new
transactions into it, recomputing totals. It never touches the status of
an already-existing certificate — new certificates always start as DRAFT
and status changes are left to the explicit Certificates-page status
control, so a later re-import can't silently downgrade progress a user
has already recorded in-app.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

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
        anchor = transaction.invoice_date or transaction.created_at
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
