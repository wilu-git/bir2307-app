import pytest

from app.core.models import EventCategory, EventLog, Payee, Payor, TaxType
from app.core.records import (
    DuplicateTinError,
    PayeeFields,
    PayorFields,
    search_payees,
    update_payee,
    update_payor,
)


def _make_payee(session, *, tin="307-265-187-000", name="Test Payee") -> Payee:
    payee = Payee(tin=tin, registered_name=name, tax_type=TaxType.NONVAT)
    session.add(payee)
    session.flush()
    return payee


def test_update_payor_saves_fields_and_logs_diff(session):
    payor = session.query(Payor).first()
    update_payor(
        session,
        payor,
        PayorFields(
            tin="000-111-222-000",
            registered_name="Favor Church PH Inc",
            address="123 Real Address",
            zip_code="1000",
        ),
        "test_user",
    )
    session.commit()

    assert payor.tin == "000-111-222-000"
    assert payor.registered_name == "Favor Church PH Inc"
    assert payor.address == "123 Real Address"

    events = session.query(EventLog).filter_by(category=EventCategory.SYSTEM).all()
    assert len(events) == 1
    assert "registered_name" in events[0].technical_detail


def test_update_payor_malformed_tin_still_saves_but_logs_warning(session):
    payor = session.query(Payor).first()
    update_payor(
        session,
        payor,
        PayorFields(
            tin="not-a-tin",
            registered_name=payor.registered_name,
            address=payor.address,
            zip_code=payor.zip_code,
        ),
        "test_user",
    )
    session.commit()

    assert payor.tin == "not-a-tin"
    tin_events = (
        session.query(EventLog).filter_by(category=EventCategory.TIN_FORMAT).all()
    )
    assert len(tin_events) == 1


def test_update_payor_no_op_when_nothing_changes_skips_log(session):
    payor = session.query(Payor).first()
    update_payor(
        session,
        payor,
        PayorFields(
            tin=payor.tin,
            registered_name=payor.registered_name,
            address=payor.address,
            zip_code=payor.zip_code,
        ),
        "test_user",
    )
    session.commit()

    events = session.query(EventLog).filter_by(category=EventCategory.SYSTEM).all()
    assert len(events) == 0


def test_update_payee_saves_fields(session):
    payee = _make_payee(session)
    update_payee(
        session,
        payee,
        PayeeFields(
            tin="307-265-187-000",
            registered_name="Updated Name",
            address="New Address",
            zip_code="2000",
            email="updated@example.com",
            tax_type=TaxType.VAT,
        ),
        "test_user",
    )
    session.commit()

    assert payee.registered_name == "Updated Name"
    assert payee.tax_type == TaxType.VAT


def test_update_payee_duplicate_tin_raises_and_does_not_save(session):
    _make_payee(session, tin="111-111-111-000", name="Existing Payee")
    other = _make_payee(session, tin="222-222-222-000", name="Other Payee")

    with pytest.raises(DuplicateTinError):
        update_payee(
            session,
            other,
            PayeeFields(
                tin="111-111-111-000",
                registered_name=other.registered_name,
                address=None,
                zip_code=None,
                email=None,
                tax_type=other.tax_type,
            ),
            "test_user",
        )
    session.rollback()
    assert other.tin == "222-222-222-000"


def test_update_payee_same_tin_is_not_a_collision(session):
    payee = _make_payee(session, tin="333-333-333-000")
    update_payee(
        session,
        payee,
        PayeeFields(
            tin="333-333-333-000",
            registered_name="Renamed",
            address=None,
            zip_code=None,
            email=None,
            tax_type=payee.tax_type,
        ),
        "test_user",
    )
    session.commit()
    assert payee.registered_name == "Renamed"


def test_search_payees_by_name_and_tin(session):
    _make_payee(session, tin="444-444-444-000", name="Alpha Supplier")
    _make_payee(session, tin="555-555-555-000", name="Beta Contractor")

    assert [p.registered_name for p in search_payees(session, name="alpha")] == [
        "Alpha Supplier"
    ]
    assert [p.registered_name for p in search_payees(session, tin="555555555")] == [
        "Beta Contractor"
    ]
    assert len(search_payees(session)) == 2
