"""Input sanitization and PII-masking helpers for TINs and free text.

TIN validation is deliberately loose on branch-code length: the real Favor
Church data contains both 3-digit (`XXX-XXX-XXX-XXX`) and 5-digit
(`XXX-XXX-XXX-XXXXX`) branch codes for genuine, already-issued TINs, so
rejecting the 5-digit shape would misflag valid historical records.
"""

from __future__ import annotations

import re

_TIN_PATTERN = re.compile(r"^\d{3}-\d{3}-\d{3}-\d{3,5}$")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_tin(raw_tin: str) -> str:
    """Trim stray whitespace/newlines a spreadsheet export tends to introduce."""
    return raw_tin.strip()


def is_valid_tin(raw_tin: str) -> bool:
    """True if `raw_tin` matches ###-###-###-### or ###-###-###-##### after trimming."""
    return bool(_TIN_PATTERN.match(normalize_tin(raw_tin)))


def mask_tin(raw_tin: str) -> str:
    """Show only the first 9 digits (owner segment); mask the branch-code segment.

    E.g. "222-228-858-00000" -> "222-228-858-XXXXX". Falls back to masking
    everything after the first 3 segments for TINs that don't match the
    strict pattern, rather than raising on already-malformed input.
    """
    tin = normalize_tin(raw_tin)
    parts = tin.split("-")
    if len(parts) == 4:
        return "-".join(parts[:3]) + "-" + "X" * len(parts[3])
    return tin


def sanitize_text(value: str | None) -> str | None:
    """Best-effort cleanup for free-text spreadsheet fields.

    Never raises on odd/mis-encoded bytes (real data contains at least one
    mojibake'd name) — strips control characters and surrounding
    whitespace, otherwise preserves content as-is so accounting notes
    aren't silently altered.
    """
    if value is None:
        return None
    cleaned = _CONTROL_CHARS.sub("", value)
    return cleaned.strip() or None
