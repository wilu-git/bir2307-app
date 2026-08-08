"""Certificate search: combinable filters by payee name, TIN, period, and
status, with pagination. Kept out of the Streamlit page so the matching
logic (case-insensitive name substring, digits-only TIN substring so a
search works whether or not the user types the dashes) is unit-testable
without a running app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models import Certificate, CertificateStatus, Payee
from app.core.text_match import contains_ci, normalize_tin_digits


@dataclass
class SearchResult:
    certificates: list[Certificate]
    total_count: int


def search_certificates(
    session: Session,
    *,
    name: str | None = None,
    tin: str | None = None,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
    status: CertificateStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> SearchResult:
    """Combinable AND filters over certificates. Certificate count in this
    app is small enough (one per payee per quarter) that name/TIN matching
    is done in Python after a DB-level date/status filter — simpler and
    more correct than emulating digits-only TIN matching in SQL.
    """
    query = session.query(Certificate).join(Payee)
    if status is not None:
        query = query.filter(Certificate.status == status)
    if period_from is not None:
        query = query.filter(Certificate.period_end >= period_from)
    if period_to is not None:
        query = query.filter(Certificate.period_start <= period_to)

    candidates = query.order_by(Certificate.id.desc()).all()

    def matches(cert: Certificate) -> bool:
        if not contains_ci(cert.payee.registered_name, name):
            return False
        if tin and tin.strip() and normalize_tin_digits(tin) not in normalize_tin_digits(cert.payee.tin):
            return False
        return True

    filtered = [c for c in candidates if matches(c)]
    total_count = len(filtered)

    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]
    return SearchResult(certificates=page_items, total_count=total_count)
