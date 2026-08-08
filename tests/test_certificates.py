from datetime import datetime
from decimal import Decimal

from app.core.certificates import (
    group_ungrouped_transactions,
    quarter_bounds,
    transition_status,
)
from app.core.models import (
    AtcCode,
    Certificate,
    CertificateStatus,
    EventCategory,
    EventLog,
    ImportBatch,
    Payee,
    Payor,
    StatusLog,
    TaxType,
    Transaction,
)


def test_quarter_bounds_q1():
    start, end = quarter_bounds(datetime(2026, 2, 15))
    assert start == datetime(2026, 1, 1)
    assert end == datetime(2026, 3, 31)


def test_quarter_bounds_q3():
    start, end = quarter_bounds(datetime(2026, 8, 6))
    assert start == datetime(2026, 7, 1)
    assert end == datetime(2026, 9, 30)


def test_quarter_bounds_q4_year_end():
    start, end = quarter_bounds(datetime(2026, 11, 1))
    assert start == datetime(2026, 10, 1)
    assert end == datetime(2026, 12, 31)


def _make_transaction(session, *, payee_tin="307-265-187-000") -> Transaction:
    payee = session.query(Payee).filter_by(tin=payee_tin).one_or_none()
    if payee is None:
        payee = Payee(tin=payee_tin, registered_name="Test Payee", tax_type=TaxType.NONVAT)
        session.add(payee)
        session.flush()
    payor = session.query(Payor).first()
    atc = session.query(AtcCode).filter_by(code="WI100").one()
    batch = ImportBatch(filename="test.xlsx", uploaded_by="test")
    session.add(batch)
    session.flush()
    transaction = Transaction(
        payee_id=payee.id,
        payor_id=payor.id,
        batch_id=batch.id,
        reference_no="FAV0001",
        atc_code=atc.code,
        total_billing=Decimal("1000"),
        gross_amount=Decimal("1000"),
        tax_base=Decimal("1000"),
        rate_applied=atc.default_rate,
        tax_withheld=Decimal("50"),
        amount_paid=Decimal("950"),
        invoice_date=datetime(2026, 8, 1),
    )
    session.add(transaction)
    session.flush()
    return transaction


def test_group_ungrouped_creates_one_certificate_per_payee_period(session):
    _make_transaction(session)
    _make_transaction(session)
    session.commit()

    certs = group_ungrouped_transactions(session)
    assert len(certs) == 1
    cert = certs[0]
    assert cert.total_gross == Decimal("2000")
    assert cert.total_tax_withheld == Decimal("100")
    assert cert.status == CertificateStatus.DRAFT


def test_group_ungrouped_is_idempotent_no_duplicate_certificates(session):
    _make_transaction(session)
    session.commit()
    first = group_ungrouped_transactions(session)
    assert len(first) == 1

    second = group_ungrouped_transactions(session)
    assert len(second) == 0  # nothing new to group

    from app.core.models import Certificate

    assert session.query(Certificate).count() == 1


def _make_certificate(session) -> Certificate:
    payee = Payee(tin="111-222-333-000", registered_name="Test Payee", tax_type=TaxType.NONVAT)
    session.add(payee)
    payor = session.query(Payor).first()
    session.flush()
    cert = Certificate(
        payee_id=payee.id,
        payor_id=payor.id,
        period_start=datetime(2026, 7, 1),
        period_end=datetime(2026, 9, 30),
        total_gross=Decimal("0"),
        total_tax_withheld=Decimal("0"),
        status=CertificateStatus.DRAFT,
    )
    session.add(cert)
    session.flush()
    return cert


def test_transition_status_writes_status_log_and_event_log(session):
    cert = _make_certificate(session)
    transition_status(session, cert, CertificateStatus.GENERATED, "test_user", "PDF generated.")
    session.commit()

    assert cert.status == CertificateStatus.GENERATED
    log = session.query(StatusLog).filter_by(certificate_id=cert.id).one()
    assert log.old_status == "draft"
    assert log.new_status == "generated"
    assert log.changed_by == "test_user"

    event = (
        session.query(EventLog)
        .filter_by(certificate_id=cert.id, category=EventCategory.STATUS_TRANSITION)
        .one()
    )
    assert "draft -> generated" in event.message


def test_transition_status_same_status_is_noop(session):
    cert = _make_certificate(session)
    transition_status(session, cert, CertificateStatus.DRAFT, "test_user")
    session.commit()

    assert session.query(StatusLog).filter_by(certificate_id=cert.id).count() == 0
