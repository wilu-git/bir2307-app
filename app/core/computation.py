"""EWT computation and mismatch-detection logic.

All monetary math uses `Decimal`, never `float` — floating point rounding
errors are unacceptable in accounting data. Rates come from the caller
(looked up from the `atc_codes` table by the importer), never hardcoded
here, so a BIR rate change is a one-row DB update.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MISMATCH_TOLERANCE = Decimal("0.01")


def compute_tax_base(gross_amount: Decimal, tax_type: str) -> Decimal:
    """VAT-registered payees: strip 12% VAT before applying the EWT rate.

    NONVAT payees: tax base equals gross amount.
    """
    if tax_type.upper() == "VAT":
        return gross_amount / Decimal("1.12")
    return gross_amount


def compute_tax_withheld(tax_base: Decimal, rate: Decimal) -> Decimal:
    """Tax base times ATC rate, rounded to centavos with ROUND_HALF_UP."""
    return (tax_base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_amount_paid(total_billing: Decimal, tax_withheld: Decimal) -> Decimal:
    """Net amount actually paid to the payee after withholding."""
    return total_billing - tax_withheld


def is_mismatch(computed: Decimal, uploaded: Decimal | None) -> bool:
    """True if `uploaded` is present and differs from `computed` by more than ₱0.01."""
    if uploaded is None:
        return False
    return abs(computed - uploaded) > MISMATCH_TOLERANCE
