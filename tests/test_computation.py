from decimal import Decimal

from app.core.computation import (
    compute_amount_paid,
    compute_tax_base,
    compute_tax_withheld,
    is_mismatch,
)


def test_tax_base_vat_strips_12_percent():
    # Real Shangri-La Plaza row: gross 232701.22 VAT -> base 207768.9464
    assert compute_tax_base(Decimal("232701.22"), "VAT") == Decimal("232701.22") / Decimal("1.12")


def test_tax_base_nonvat_equals_gross():
    assert compute_tax_base(Decimal("42710.00"), "NONVAT") == Decimal("42710.00")


def test_tax_base_case_insensitive():
    assert compute_tax_base(Decimal("100"), "vat") == Decimal("100") / Decimal("1.12")


def test_tax_withheld_rounds_half_up():
    # 5571.428571 * 0.02 = 111.4285714... -> rounds to 111.43 (real WC160 row)
    result = compute_tax_withheld(Decimal("5571.428571"), Decimal("0.02"))
    assert result == Decimal("111.43")


def test_tax_withheld_real_wi100_row():
    # Real row: base 42710, rate 5% -> 2135.50
    assert compute_tax_withheld(Decimal("42710"), Decimal("0.05")) == Decimal("2135.50")


def test_amount_paid_subtracts_tax_withheld():
    assert compute_amount_paid(Decimal("42710"), Decimal("2135.50")) == Decimal("40574.50")


def test_is_mismatch_within_tolerance_is_false():
    assert is_mismatch(Decimal("100.00"), Decimal("100.005")) is False


def test_is_mismatch_beyond_tolerance_is_true():
    assert is_mismatch(Decimal("100.00"), Decimal("100.02")) is True


def test_is_mismatch_none_uploaded_is_false():
    assert is_mismatch(Decimal("100.00"), None) is False
