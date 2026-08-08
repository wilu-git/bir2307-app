"""Payee-centric queries for the unified Payees screen.

Combines a payee's identity (name/TIN/tax type) with a summary of their
certificates, and looks up one payee's certificates for the detail pane.
Dataset is small (one certificate per payee per quarter), so filtering by
quarter/date/status happens in Python, same approach already used by
`core/search.py` and `core/records.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models import Certificate, CertificateStatus, Payee
from app.core.records import search_payees


@dataclass
class PayeeSummary:
    payee: Payee
    certificate_count: int
    matching_certificate_count: int
    latest_status: CertificateStatus | None


def quarter_bounds(year: int, quarter: int) -> tuple[datetime, datetime]:
    """(period_start, period_end) for calendar quarter `quarter` of `year`."""
    first_month = (quarter - 1) * 3 + 1
    start = datetime(year, first_month, 1)
    if first_month + 3 > 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, first_month + 3, 1)
    return start, end


def list_quarter_options(*, start_year: int = 2023) -> list[tuple[int, int]]:
    """(year, quarter) pairs from `start_year` through next calendar year,
    newest first — a small generated range, not a DB query."""
    current_year = datetime.now().year
    options = [
        (year, quarter)
        for year in range(start_year, current_year + 2)
        for quarter in range(1, 5)
    ]
    return list(reversed(options))


def _certificate_matches(
    certificate: Certificate,
    *,
    period_from: datetime | None,
    period_to: datetime | None,
    status: CertificateStatus | None,
) -> bool:
    if status is not None and certificate.status != status:
        return False
    if period_from is not None and certificate.period_end < period_from:
        return False
    if period_to is not None and certificate.period_start > period_to:
        return False
    return True


def list_payees_with_summary(
    session: Session,
    *,
    name: str | None = None,
    tin: str | None = None,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
    status: CertificateStatus | None = None,
) -> list[PayeeSummary]:
    """Payees matching name/TIN, each with certificate counts under the
    active period/status filter."""
    payees = search_payees(session, name=name, tin=tin)

    summaries: list[PayeeSummary] = []
    for payee in payees:
        certificates = payee.certificates
        matching = [
            c
            for c in certificates
            if _certificate_matches(c, period_from=period_from, period_to=period_to, status=status)
        ]
        latest_status = None
        if certificates:
            latest_status = max(certificates, key=lambda c: c.id).status
        summaries.append(
            PayeeSummary(
                payee=payee,
                certificate_count=len(certificates),
                matching_certificate_count=len(matching),
                latest_status=latest_status,
            )
        )
    return summaries


def get_certificates_for_payee(
    session: Session,
    payee_id: int,
    *,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
    status: CertificateStatus | None = None,
) -> list[Certificate]:
    """All of one payee's certificates matching the active period/status
    filter, newest first — so the detail pane stays consistent with the
    filters applied in the list."""
    query = session.query(Certificate).filter(Certificate.payee_id == payee_id)
    if status is not None:
        query = query.filter(Certificate.status == status)
    if period_from is not None:
        query = query.filter(Certificate.period_end >= period_from)
    if period_to is not None:
        query = query.filter(Certificate.period_start <= period_to)
    return query.order_by(Certificate.id.desc()).all()
