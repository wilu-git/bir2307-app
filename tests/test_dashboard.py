from datetime import datetime
from decimal import Decimal

from app.core.certificates import quarter_bounds
from app.core.dashboard import (
    attention_items,
    quarter_kpis,
    quarterly_summary,
    recent_activity,
    workflow_stage_counts,
)
from app.core.logging_config import log_event
from app.core.models import (
    AtcCode,
    Certificate,
    CertificateStatus,
    EventCategory,
    EventSeverity,
    ImportBatch,
    Payee,
    Payor,
    TaxType,
    Transaction,
)
from app.core.pdf_generator import MAX_ATC_LINES_PER_CERTIFICATE

Q3_START, Q3_END = quarter_bounds(datetime(2026, 8, 1))


def _make_payee(session, *, tin="307-265-187-000", name="Test Payee") -> Payee:
    payee = Payee(tin=tin, registered_name=name, tax_type=TaxType.NONVAT)
    session.add(payee)
    session.flush()
    return payee


def _make_certificate(
    session,
    *,
    status=CertificateStatus.DRAFT,
    period_start=Q3_START,
    period_end=Q3_END,
    total_gross=Decimal("1000"),
    total_tax_withheld=Decimal("50"),
    pdf_signed_path=None,
    payee=None,
) -> Certificate:
    payee = payee or _make_payee(session, tin=f"{session.query(Payee).count():03d}-000-000-000")
    payor = session.query(Payor).first()
    cert = Certificate(
        payee_id=payee.id,
        payor_id=payor.id,
        period_start=period_start,
        period_end=period_end,
        total_gross=total_gross,
        total_tax_withheld=total_tax_withheld,
        status=status,
        pdf_signed_path=pdf_signed_path,
    )
    session.add(cert)
    session.flush()
    return cert


def _link_transaction(session, certificate, atc_code="WI100") -> Transaction:
    payor = session.query(Payor).first()
    batch = ImportBatch(filename="t.xlsx", uploaded_by="test")
    session.add(batch)
    session.flush()
    if not session.query(AtcCode).filter_by(code=atc_code).count():
        session.add(AtcCode(code=atc_code, description="Test", default_rate="0.05"))
        session.flush()
    txn = Transaction(
        batch_id=batch.id,
        payee_id=certificate.payee_id,
        payor_id=payor.id,
        reference_no=f"REF-{atc_code}-{certificate.id}",
        atc_code=atc_code,
        total_billing=1000,
        gross_amount=1000,
        tax_base=1000,
        rate_applied="0.05",
        tax_withheld=50,
        amount_paid=950,
    )
    session.add(txn)
    session.flush()
    from app.core.models import CertificateTransaction

    session.add(CertificateTransaction(certificate_id=certificate.id, transaction_id=txn.id))
    session.flush()
    return txn


def test_quarter_kpis_counts_by_status(session):
    _make_certificate(session, status=CertificateStatus.DRAFT)
    _make_certificate(session, status=CertificateStatus.GENERATED)
    _make_certificate(session, status=CertificateStatus.FORWARDED)
    _make_certificate(session, status=CertificateStatus.COMPLETED_SIGNED)
    session.commit()

    kpis = quarter_kpis(session, Q3_START, Q3_END)
    assert kpis.generated == 3  # generated + forwarded + completed_signed, not draft
    assert kpis.forwarded == 1
    assert kpis.completed == 1


def test_quarter_kpis_for_review_counts_certs_with_unresolved_warnings(session):
    cert = _make_certificate(session, status=CertificateStatus.DRAFT)
    log_event(
        session,
        category=EventCategory.COMPUTATION_MISMATCH,
        severity=EventSeverity.WARNING,
        message="mismatch",
        certificate_id=cert.id,
    )
    session.commit()

    kpis = quarter_kpis(session, Q3_START, Q3_END)
    assert kpis.for_review == 1


def test_quarter_kpis_ignores_resolved_events(session):
    cert = _make_certificate(session, status=CertificateStatus.DRAFT)
    event = log_event(
        session,
        category=EventCategory.COMPUTATION_MISMATCH,
        severity=EventSeverity.WARNING,
        message="mismatch",
        certificate_id=cert.id,
    )
    event.resolved_by = "someone"
    event.resolved_at = datetime.now()
    session.commit()

    kpis = quarter_kpis(session, Q3_START, Q3_END)
    assert kpis.for_review == 0


def test_quarter_kpis_exceptions_flags_atc_overflow(session):
    cert = _make_certificate(session, status=CertificateStatus.GENERATED)
    for i in range(MAX_ATC_LINES_PER_CERTIFICATE + 1):
        _link_transaction(session, cert, atc_code=f"CODE{i}")
    session.commit()

    kpis = quarter_kpis(session, Q3_START, Q3_END)
    assert kpis.exceptions == 1


def test_quarter_kpis_excludes_certs_outside_period(session):
    _make_certificate(
        session,
        status=CertificateStatus.GENERATED,
        period_start=datetime(2025, 1, 1),
        period_end=datetime(2025, 3, 31),
    )
    session.commit()

    kpis = quarter_kpis(session, Q3_START, Q3_END)
    assert kpis.generated == 0


def test_workflow_stage_counts(session):
    _make_certificate(session, status=CertificateStatus.DRAFT)
    _make_certificate(session, status=CertificateStatus.DRAFT)
    _make_certificate(session, status=CertificateStatus.VOID)
    session.commit()

    counts = workflow_stage_counts(session, Q3_START, Q3_END)
    assert counts.draft == 2
    assert counts.void == 1
    assert counts.generated == 0


def test_attention_items_flags_missing_signed_copies(session):
    _make_certificate(session, status=CertificateStatus.FORWARDED, pdf_signed_path=None)
    session.commit()

    items = attention_items(session, Q3_START, Q3_END, payor_is_placeholder=False)
    assert any("missing signed" in i.title for i in items)


def test_attention_items_flags_placeholder_payor(session):
    items = attention_items(session, Q3_START, Q3_END, payor_is_placeholder=True)
    assert any("placeholder" in i.title.lower() for i in items)


def test_attention_items_empty_when_nothing_wrong(session):
    items = attention_items(session, Q3_START, Q3_END, payor_is_placeholder=False)
    assert items == []


def test_recent_activity_orders_newest_first_and_respects_limit(session):
    for i in range(5):
        log_event(
            session,
            category=EventCategory.SYSTEM,
            severity=EventSeverity.INFO,
            message=f"event {i}",
        )
    session.commit()

    activity = recent_activity(session, limit=3)
    assert len(activity) == 3
    assert activity[0].message == "event 4"


def test_quarterly_summary_totals_and_status_counts(session):
    _make_certificate(
        session,
        status=CertificateStatus.GENERATED,
        total_gross=Decimal("1000"),
        total_tax_withheld=Decimal("50"),
    )
    _make_certificate(
        session,
        status=CertificateStatus.FORWARDED,
        total_gross=Decimal("2000"),
        total_tax_withheld=Decimal("100"),
    )
    session.commit()

    summary = quarterly_summary(session, Q3_START, Q3_END)
    assert summary.certificate_count == 2
    assert summary.payee_count == 2
    assert summary.total_ewt == Decimal("150")
    assert summary.total_amount_paid == Decimal("2850")  # (1000-50)+(2000-100)
    assert summary.status_counts["generated"] == 1
    assert summary.status_counts["forwarded"] == 1
