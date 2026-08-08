"""Shared text-matching helpers for payee/certificate search.

Case-insensitive name-substring matching and digits-only TIN-substring
matching (so a search works whether or not the user types the dashes) were
previously duplicated independently in `core/search.py` and `core/records.py`.
Both now import from here instead.
"""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D+")


def normalize_tin_digits(value: str) -> str:
    """Strip everything but digits, so TIN matching ignores dashes."""
    return _NON_DIGITS.sub("", value)


def contains_ci(haystack: str, needle: str | None) -> bool:
    """Case-insensitive substring check. A blank/None needle always matches."""
    if not needle or not needle.strip():
        return True
    return needle.strip().lower() in haystack.lower()
