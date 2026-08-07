import dataclasses

from app.core import demo_seed
from app.core.models import Certificate, EventLog, Payee, Payor


def _enable_demo_mode(monkeypatch, tmp_path):
    demo_settings = dataclasses.replace(
        demo_seed.settings, demo_mode=True, generated_pdfs_dir=tmp_path
    )
    monkeypatch.setattr(demo_seed, "settings", demo_settings)
    return demo_settings


def test_seed_demo_data_noop_when_demo_mode_off(session, monkeypatch, tmp_path):
    demo_settings = dataclasses.replace(demo_seed.settings, demo_mode=False)
    monkeypatch.setattr(demo_seed, "settings", demo_settings)

    demo_seed.seed_demo_data(session)

    assert session.query(Payee).count() == 0


def test_seed_demo_data_populates_payees_and_certificates(
    session, monkeypatch, tmp_path
):
    _enable_demo_mode(monkeypatch, tmp_path)

    demo_seed.seed_demo_data(session)

    assert session.query(Payee).count() > 0
    assert session.query(Certificate).count() > 0

    payor = session.query(Payor).first()
    assert payor.registered_name == demo_seed.DEMO_PAYOR["registered_name"]

    # The demo rows are crafted to exercise every logged event category.
    categories = {e.category.value for e in session.query(EventLog).all()}
    assert "TIN_FORMAT" in categories
    assert "ATC_RATE_UNKNOWN" in categories
    assert "DUPLICATE_REFERENCE" in categories
    assert "ROW_VALIDATION" in categories


def test_seed_demo_data_never_overwrites_existing_payees(
    session, monkeypatch, tmp_path
):
    _enable_demo_mode(monkeypatch, tmp_path)

    from app.core.models import TaxType

    real_payee = Payee(
        tin="900-900-900-000", registered_name="Real Payee", tax_type=TaxType.NONVAT
    )
    session.add(real_payee)
    session.commit()

    demo_seed.seed_demo_data(session)

    payees = session.query(Payee).all()
    assert len(payees) == 1
    assert payees[0].registered_name == "Real Payee"


def test_seed_demo_data_is_idempotent(session, monkeypatch, tmp_path):
    _enable_demo_mode(monkeypatch, tmp_path)

    demo_seed.seed_demo_data(session)
    first_count = session.query(Payee).count()

    demo_seed.seed_demo_data(session)
    second_count = session.query(Payee).count()

    assert first_count == second_count
