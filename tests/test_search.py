from datetime import datetime
from decimal import Decimal

from app.core.search import search_certificates
from app.core.models import Certificate, CertificateStatus, Payee, TaxType


def _make_cert(
    session,
    *,
    tin,
    name,
    status=CertificateStatus.DRAFT,
    period_start=datetime(2026, 7, 1),
    period_end=datetime(2026, 9, 30),
):
    from app.core.models import Payor

    payee = Payee(tin=tin, registered_name=name, tax_type=TaxType.NONVAT)
    session.add(payee)
    payor = session.query(Payor).first()
    session.flush()
    cert = Certificate(
        payee_id=payee.id,
        payor_id=payor.id,
        period_start=period_start,
        period_end=period_end,
        total_gross=Decimal("1000"),
        total_tax_withheld=Decimal("50"),
        status=status,
    )
    session.add(cert)
    session.flush()
    return cert


def test_search_by_name_case_insensitive_substring(session):
    _make_cert(session, tin="111-111-111-000", name="Shangri-La Plaza Corporation")
    _make_cert(session, tin="222-222-222-000", name="Clean Zone PH Inc.")
    session.commit()

    result = search_certificates(session, name="shangri")
    assert result.total_count == 1
    assert result.certificates[0].payee.registered_name == "Shangri-La Plaza Corporation"


def test_search_by_tin_ignores_dashes_in_query(session):
    _make_cert(session, tin="307-265-187-000", name="Vendor A")
    session.commit()

    result = search_certificates(session, tin="307265187")
    assert result.total_count == 1


def test_search_by_tin_partial_match(session):
    _make_cert(session, tin="307-265-187-000", name="Vendor A")
    session.commit()

    result = search_certificates(session, tin="265-187")
    assert result.total_count == 1


def test_search_by_status(session):
    _make_cert(session, tin="111-111-111-000", name="Draft Vendor", status=CertificateStatus.DRAFT)
    _make_cert(
        session,
        tin="222-222-222-000",
        name="Signed Vendor",
        status=CertificateStatus.COMPLETED_SIGNED,
    )
    session.commit()

    result = search_certificates(session, status=CertificateStatus.COMPLETED_SIGNED)
    assert result.total_count == 1
    assert result.certificates[0].payee.registered_name == "Signed Vendor"


def test_search_by_period_overlap(session):
    _make_cert(
        session,
        tin="111-111-111-000",
        name="Q3 Vendor",
        period_start=datetime(2026, 7, 1),
        period_end=datetime(2026, 9, 30),
    )
    _make_cert(
        session,
        tin="222-222-222-000",
        name="Q1 Vendor",
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 3, 31),
    )
    session.commit()

    result = search_certificates(
        session, period_from=datetime(2026, 6, 1), period_to=datetime(2026, 12, 31)
    )
    assert result.total_count == 1
    assert result.certificates[0].payee.registered_name == "Q3 Vendor"


def test_search_combines_filters_with_and(session):
    _make_cert(session, tin="111-111-111-000", name="Match Vendor", status=CertificateStatus.DRAFT)
    _make_cert(
        session, tin="222-222-222-000", name="Match Vendor", status=CertificateStatus.FORWARDED
    )
    session.commit()

    result = search_certificates(session, name="match", status=CertificateStatus.FORWARDED)
    assert result.total_count == 1
    assert result.certificates[0].payee.tin == "222-222-222-000"


def test_search_pagination(session):
    for i in range(5):
        _make_cert(session, tin=f"{i:03d}-111-111-000", name=f"Vendor {i}")
    session.commit()

    page1 = search_certificates(session, page=1, page_size=2)
    page2 = search_certificates(session, page=2, page_size=2)
    assert page1.total_count == 5
    assert len(page1.certificates) == 2
    assert len(page2.certificates) == 2
    assert {c.id for c in page1.certificates}.isdisjoint({c.id for c in page2.certificates})


def test_search_no_filters_returns_all(session):
    _make_cert(session, tin="111-111-111-000", name="Vendor A")
    _make_cert(session, tin="222-222-222-000", name="Vendor B")
    session.commit()

    result = search_certificates(session)
    assert result.total_count == 2
