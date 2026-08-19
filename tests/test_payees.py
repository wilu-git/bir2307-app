from datetime import datetime
from decimal import Decimal

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
from app.core.payees import get_events_for_payee, get_transactions_for_payee, quarter_bounds


def _make_payee(session, *, tin="307-265-187-000", name="Test Payee") -> Payee:
    payee = Payee(tin=tin, registered_name=name, tax_type=TaxType.NONVAT)
    session.add(payee)
    session.flush()
    return payee


def _make_transaction(session, payee, *, invoice_date=None) -> Transaction:
    payor = session.query(Payor).first()
    atc = session.query(AtcCode).filter_by(code="WI100").one()
    batch = ImportBatch(filename="t.xlsx", uploaded_by="test")
    session.add(batch)
    session.flush()
    txn = Transaction(
        batch_id=batch.id,
        payee_id=payee.id,
        payor_id=payor.id,
        reference_no="REF-1",
        atc_code=atc.code,
        total_billing=Decimal("1000"),
        gross_amount=Decimal("1000"),
        tax_base=Decimal("1000"),
        rate_applied=atc.default_rate,
        tax_withheld=Decimal("50"),
        amount_paid=Decimal("950"),
        invoice_date=invoice_date,
    )
    session.add(txn)
    session.flush()
    return txn


def test_get_transactions_for_payee_only_returns_that_payees_rows(session):
    payee1 = _make_payee(session, tin="111-111-111-000", name="Payee One")
    payee2 = _make_payee(session, tin="222-222-222-000", name="Payee Two")
    _make_transaction(session, payee1, invoice_date=datetime(2026, 1, 1))
    _make_transaction(session, payee1, invoice_date=datetime(2026, 3, 1))
    _make_transaction(session, payee2)
    session.commit()

    results = get_transactions_for_payee(session, payee1.id)
    assert len(results) == 2
    assert all(t.payee_id == payee1.id for t in results)
    # newest invoice_date first
    assert results[0].invoice_date == datetime(2026, 3, 1)


def test_get_events_for_payee_returns_empty_when_no_activity(session):
    payee = _make_payee(session)
    session.commit()
    assert get_events_for_payee(session, payee.id) == []


def test_get_events_for_payee_finds_events_via_transaction_and_certificate(session):
    payee = _make_payee(session)
    txn = _make_transaction(session, payee)
    cert = Certificate(
        payee_id=payee.id,
        payor_id=txn.payor_id,
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 3, 31),
        total_gross=Decimal("0"),
        total_tax_withheld=Decimal("0"),
        status=CertificateStatus.DRAFT,
    )
    session.add(cert)
    session.flush()

    log_event(
        session,
        category=EventCategory.ROW_VALIDATION,
        severity=EventSeverity.WARNING,
        message="via transaction",
        transaction_id=txn.id,
    )
    log_event(
        session,
        category=EventCategory.STATUS_TRANSITION,
        severity=EventSeverity.INFO,
        message="via certificate",
        certificate_id=cert.id,
    )
    session.commit()

    events = get_events_for_payee(session, payee.id)
    assert {e.message for e in events} == {"via transaction", "via certificate"}


def test_get_events_for_payee_excludes_other_payees_events(session):
    payee1 = _make_payee(session, tin="333-333-333-000")
    payee2 = _make_payee(session, tin="444-444-444-000")
    txn2 = _make_transaction(session, payee2)
    log_event(
        session,
        category=EventCategory.ROW_VALIDATION,
        severity=EventSeverity.WARNING,
        message="belongs to payee2",
        transaction_id=txn2.id,
    )
    session.commit()

    assert get_events_for_payee(session, payee1.id) == []


def test_quarter_bounds_end_is_inclusive_last_day():
    """Regression: an exclusive "start of next quarter" end previously made
    Certificate.period_start <= period_to (used throughout search/dashboard)
    incorrectly admit next-quarter certificates whose period_start lands
    exactly on that boundary — see app/core/certificates.quarter_bounds for
    the matching inclusive-end convention certificates are actually stored
    with."""
    start, end = quarter_bounds(2026, 1)
    assert start == datetime(2026, 1, 1)
    assert end == datetime(2026, 3, 31)

    # A Q2 certificate's period_start must NOT satisfy period_start <= Q1's end.
    q2_start, _ = quarter_bounds(2026, 2)
    assert not (q2_start <= end)


def test_quarter_bounds_year_end():
    start, end = quarter_bounds(2026, 4)
    assert start == datetime(2026, 10, 1)
    assert end == datetime(2026, 12, 31)
