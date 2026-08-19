"""Read-only aggregate queries for the Overview dashboard and Reports page.

Every function here is a pure SELECT over tables the rest of app/core/
already writes (certificates, event_logs, transactions, payees) — no new
schema, no new business rules. Mirrors the read-aggregation pattern already
used by `payees.list_payees_with_summary`.

Metric definitions (there is no single canonical meaning for e.g. "For
Review" — these are the concrete, honest choices made here):

- generated: certificates in the period that have left DRAFT and aren't
  VOID (i.e. at least a PDF has been produced for them).
- for_review: certificates in the period with an unresolved WARNING-or
  worse event_log entry attached (mismatch, TIN format, duplicate, unknown
  ATC, etc.) — something a preparer should look at before forwarding.
- forwarded / completed: certificates in the period currently at that
  exact CertificateStatus.
- exceptions: certificates in the period with an unresolved ERROR-severity
  event, or with more distinct ATC codes than the PDF template's Part III
  table can render without rows overlapping (see
  `pdf_generator.MAX_ATC_LINES_PER_CERTIFICATE`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.models import Certificate, CertificateStatus, EventLog, EventSeverity, Payee
from app.core.pdf_generator import MAX_ATC_LINES_PER_CERTIFICATE, count_distinct_atc_codes


def _certs_in_period(
    session: Session, period_start: datetime, period_end: datetime
) -> list[Certificate]:
    return (
        session.query(Certificate)
        .filter(Certificate.period_end >= period_start, Certificate.period_start <= period_end)
        .all()
    )


def _unresolved_events_by_certificate(
    session: Session, cert_ids: list[int], *, min_severity: EventSeverity
) -> dict[int, list[EventLog]]:
    if not cert_ids:
        return {}
    severities = (
        [EventSeverity.WARNING, EventSeverity.ERROR]
        if min_severity == EventSeverity.WARNING
        else [EventSeverity.ERROR]
    )
    rows = (
        session.query(EventLog)
        .filter(
            EventLog.certificate_id.in_(cert_ids),
            EventLog.severity.in_(severities),
            EventLog.resolved_at.is_(None),
        )
        .all()
    )
    by_cert: dict[int, list[EventLog]] = {}
    for row in rows:
        by_cert.setdefault(row.certificate_id, []).append(row)
    return by_cert


@dataclass
class QuarterKpis:
    generated: int
    for_review: int
    forwarded: int
    completed: int
    exceptions: int


def quarter_kpis(session: Session, period_start: datetime, period_end: datetime) -> QuarterKpis:
    certs = _certs_in_period(session, period_start, period_end)
    cert_ids = [c.id for c in certs]
    warn_or_worse = _unresolved_events_by_certificate(session, cert_ids, min_severity=EventSeverity.WARNING)
    errors_only = _unresolved_events_by_certificate(session, cert_ids, min_severity=EventSeverity.ERROR)

    exceptions = 0
    for c in certs:
        if c.status == CertificateStatus.VOID:
            continue
        if c.id in errors_only or count_distinct_atc_codes(session, c) > MAX_ATC_LINES_PER_CERTIFICATE:
            exceptions += 1

    return QuarterKpis(
        generated=sum(
            1 for c in certs if c.status not in (CertificateStatus.DRAFT, CertificateStatus.VOID)
        ),
        for_review=sum(1 for c in certs if c.id in warn_or_worse),
        forwarded=sum(1 for c in certs if c.status == CertificateStatus.FORWARDED),
        completed=sum(1 for c in certs if c.status == CertificateStatus.COMPLETED_SIGNED),
        exceptions=exceptions,
    )


@dataclass
class WorkflowStageCounts:
    draft: int = 0
    generated: int = 0
    forwarded: int = 0
    completed_signed: int = 0
    void: int = 0

    def as_stages(self) -> list[tuple[str, str, int]]:
        """(status_value, human_label, count) in workflow order, Void last."""
        return [
            (CertificateStatus.DRAFT.value, "Draft", self.draft),
            (CertificateStatus.GENERATED.value, "Generated", self.generated),
            (CertificateStatus.FORWARDED.value, "Forwarded", self.forwarded),
            (CertificateStatus.COMPLETED_SIGNED.value, "Signed", self.completed_signed),
            (CertificateStatus.VOID.value, "Void", self.void),
        ]


def workflow_stage_counts(session: Session, period_start: datetime, period_end: datetime) -> WorkflowStageCounts:
    counts = WorkflowStageCounts()
    for c in _certs_in_period(session, period_start, period_end):
        if c.status == CertificateStatus.DRAFT:
            counts.draft += 1
        elif c.status == CertificateStatus.GENERATED:
            counts.generated += 1
        elif c.status == CertificateStatus.FORWARDED:
            counts.forwarded += 1
        elif c.status == CertificateStatus.COMPLETED_SIGNED:
            counts.completed_signed += 1
        elif c.status == CertificateStatus.VOID:
            counts.void += 1
    return counts


@dataclass
class AttentionItem:
    title: str
    description: str
    cta_label: str
    target_view: str  # "certificates" | "settings"
    severity: str  # "warning" | "info" | "error"


def attention_items(
    session: Session, period_start: datetime, period_end: datetime, *, payor_is_placeholder: bool
) -> list[AttentionItem]:
    """Real, derived "needs attention" items — never fabricated counts."""
    items: list[AttentionItem] = []
    certs = _certs_in_period(session, period_start, period_end)
    cert_ids = [c.id for c in certs]

    warn_or_worse = _unresolved_events_by_certificate(session, cert_ids, min_severity=EventSeverity.WARNING)
    total_unresolved = sum(len(v) for v in warn_or_worse.values())
    if warn_or_worse:
        items.append(
            AttentionItem(
                title=f"{len(warn_or_worse)} certificate(s) need review",
                description=(
                    f"{total_unresolved} unresolved warning/error event(s) — mismatches, "
                    "invalid TINs, duplicates, or unrecognized ATC codes."
                ),
                cta_label="Review certificates",
                target_view="certificates",
                severity="warning",
            )
        )

    missing_signed = [
        c
        for c in certs
        if c.status == CertificateStatus.FORWARDED and not c.pdf_signed_path
    ]
    if missing_signed:
        items.append(
            AttentionItem(
                title=f"{len(missing_signed)} certificate(s) missing signed copies",
                description="Forwarded to payees but no signed copy has been uploaded yet.",
                cta_label="View certificates",
                target_view="certificates",
                severity="info",
            )
        )

    overflow = [
        c
        for c in certs
        if c.status != CertificateStatus.VOID
        and count_distinct_atc_codes(session, c) > MAX_ATC_LINES_PER_CERTIFICATE
    ]
    if overflow:
        items.append(
            AttentionItem(
                title=f"{len(overflow)} certificate(s) have too many ATC line items",
                description=(
                    f"More than {MAX_ATC_LINES_PER_CERTIFICATE} distinct ATC codes — rows will "
                    "overlap on the printed PDF. Split or review before generating."
                ),
                cta_label="Review certificates",
                target_view="certificates",
                severity="warning",
            )
        )

    if payor_is_placeholder:
        items.append(
            AttentionItem(
                title="Payor identity is still a placeholder",
                description=(
                    "Certificates will print the placeholder TIN/address until the real payor "
                    "record is set."
                ),
                cta_label="Set up organization",
                target_view="settings",
                severity="error",
            )
        )

    return items


@dataclass
class ActivityEntry:
    timestamp: datetime
    message: str
    category: str
    severity: str


def recent_activity(session: Session, limit: int = 8) -> list[ActivityEntry]:
    """The most recent event_log rows, newest first.

    `event_logs` has no dedicated actor column (unlike `status_log`'s
    `changed_by`) — the single-shared-login model means most events can't
    be reliably attributed to an individual, so this deliberately doesn't
    fabricate a "by <name>" for events that don't structurally carry one.
    """
    rows = session.query(EventLog).order_by(EventLog.created_at.desc(), EventLog.id.desc()).limit(limit).all()
    return [
        ActivityEntry(
            timestamp=row.created_at,
            message=row.message,
            category=row.category.value,
            severity=row.severity.value,
        )
        for row in rows
    ]


@dataclass
class QuarterlySummary:
    certificate_count: int
    payee_count: int
    total_amount_paid: Decimal
    total_ewt: Decimal
    status_counts: dict[str, int] = field(default_factory=dict)


def quarterly_summary(session: Session, period_start: datetime, period_end: datetime) -> QuarterlySummary:
    certs = _certs_in_period(session, period_start, period_end)
    status_counts: dict[str, int] = {s.value: 0 for s in CertificateStatus}
    total_paid = Decimal("0")
    total_ewt = Decimal("0")
    payee_ids: set[int] = set()
    for c in certs:
        status_counts[c.status.value] += 1
        total_paid += c.total_gross - c.total_tax_withheld
        total_ewt += c.total_tax_withheld
        payee_ids.add(c.payee_id)

    return QuarterlySummary(
        certificate_count=len(certs),
        payee_count=len(payee_ids),
        total_amount_paid=total_paid,
        total_ewt=total_ewt,
        status_counts=status_counts,
    )
