from decimal import Decimal

import pytest

from app.core.import_excel import (
    RowParseError,
    find_duplicate_groups,
    normalize_header,
    parse_row,
)


def _raw_row(**overrides) -> dict:
    base = {
        "bill no.": "FAV20260000000001",
        "corporate name": "SAMPLE VENDOR INC.",
        "corporate address": "123 Sample St, Quezon City",
        "zip code": None,
        "tin number": "307-265-187-000",
        "tax code": "WI100",
        "vat / nonvat": "NONVAT",
        "not subject to ewt": None,
        "total billing": "24000",
        "gross amount": "24000.0",
        "amount paid": "22800.0",
        "amount at 2307": "24000",
        "tax withheld": "1200",
        "date accomplished": None,
    }
    base.update(overrides)
    return base


def test_normalize_header_collapses_embedded_newline():
    assert normalize_header("Signed Copy \nGoogle Drive") == "signed copy google drive"


def test_parse_row_maps_confirmed_columns():
    row = parse_row(_raw_row(), row_number=2)
    assert row.reference_no == "FAV20260000000001"
    assert row.tin == "307-265-187-000"
    assert row.atc_code == "WI100"
    assert row.tax_type == "NONVAT"
    assert row.gross_amount == Decimal("24000.0")


def test_parse_row_uppercases_lowercase_atc_code():
    # Real data has a stray "wc160" alongside "WC160".
    row = parse_row(_raw_row(**{"tax code": "wc160"}), row_number=2)
    assert row.atc_code == "WC160"


def test_parse_row_missing_tin_raises():
    with pytest.raises(RowParseError):
        parse_row(_raw_row(**{"tin number": None}), row_number=2)


def test_parse_row_missing_bill_no_raises():
    with pytest.raises(RowParseError):
        parse_row(_raw_row(**{"bill no.": None}), row_number=2)


def test_parse_row_missing_gross_amount_raises():
    with pytest.raises(RowParseError):
        parse_row(_raw_row(**{"gross amount": None}), row_number=2)


def test_parse_row_falls_back_total_billing_to_gross():
    row = parse_row(_raw_row(**{"total billing": None}), row_number=2)
    assert row.total_billing == row.gross_amount


def test_duplicate_groups_identical_amounts_collapse():
    rows = [
        parse_row(_raw_row(), row_number=2),
        parse_row(_raw_row(), row_number=3),  # exact duplicate of row 2
        parse_row(_raw_row(**{"bill no.": "FAV20260000000002"}), row_number=4),
    ]
    groups = find_duplicate_groups(rows)
    assert len(groups) == 1
    assert groups[0].is_accidental_duplicate is True
    assert groups[0].indices == [0, 1]


def test_duplicate_groups_differing_amounts_merge():
    rows = [
        parse_row(_raw_row(), row_number=2),
        parse_row(_raw_row(**{"gross amount": "30000.0"}), row_number=3),
    ]
    groups = find_duplicate_groups(rows)
    assert len(groups) == 1
    assert groups[0].is_accidental_duplicate is False


def test_duplicate_groups_different_tin_same_bill_no_not_grouped():
    rows = [
        parse_row(_raw_row(), row_number=2),
        parse_row(_raw_row(**{"tin number": "002-116-558-000"}), row_number=3),
    ]
    assert find_duplicate_groups(rows) == []
