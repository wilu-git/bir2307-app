"""Saved Excel column-mapping profiles.

Lets a user remap which spreadsheet column feeds which internal field
(instead of relying on the hardcoded `import_excel.COLUMN_MAP`), and reuse
that mapping on future uploads. Follows the same "small DB-editable config
table" pattern already used for `AtcCode`.
"""

from __future__ import annotations

from difflib import get_close_matches

from sqlalchemy.orm import Session

from app.core.import_excel import COLUMN_MAP
from app.core.models import ImportColumnMapping

# Every internal field a mapping UI should let the user assign a source
# column to — derived from COLUMN_MAP rather than re-typed, so it can never
# drift out of sync with the default mapping.
INTERNAL_FIELDS = sorted(set(COLUMN_MAP.values()))


def save_profile(
    session: Session, name: str, sheet_name: str | None, mapping: dict[str, str]
) -> ImportColumnMapping:
    """Create a new profile, or overwrite the existing one with this name."""
    profile = session.query(ImportColumnMapping).filter_by(name=name).one_or_none()
    if profile is None:
        profile = ImportColumnMapping(name=name)
        session.add(profile)
    profile.sheet_name = sheet_name
    profile.mapping = mapping
    session.flush()
    return profile


def list_profiles(session: Session) -> list[ImportColumnMapping]:
    return session.query(ImportColumnMapping).order_by(ImportColumnMapping.name).all()


def get_profile(session: Session, profile_id: int) -> ImportColumnMapping | None:
    return session.get(ImportColumnMapping, profile_id)


def delete_profile(session: Session, profile_id: int) -> None:
    profile = session.get(ImportColumnMapping, profile_id)
    if profile is not None:
        session.delete(profile)
        session.flush()


def suggest_mapping(
    detected_headers: list[str], saved_profiles: list[ImportColumnMapping]
) -> dict[str, str | None]:
    """Best-guess internal field for each detected (normalized) header.

    In order, per header:
    1. Exact match against COLUMN_MAP's own keys (the unmodified-spreadsheet
       case — no fuzzy logic needed at all).
    2. Exact match against any saved profile's known headers (most recently
       updated profile wins on conflict).
    3. Fuzzy match (stdlib difflib) against the union of every header this
       app has ever seen a field assigned to.
    4. Otherwise left unmapped, so the UI can surface it instead of the
       silent drop that happens today for unrecognized columns.
    """
    profiles_newest_first = sorted(
        saved_profiles, key=lambda p: p.updated_at, reverse=True
    )

    known_headers: dict[str, str] = dict(COLUMN_MAP)
    for profile in reversed(profiles_newest_first):  # oldest first so newest overwrites
        known_headers.update(profile.mapping)

    suggestions: dict[str, str | None] = {}
    for header in detected_headers:
        if header in COLUMN_MAP:
            suggestions[header] = COLUMN_MAP[header]
            continue

        exact_profile_match = next(
            (p.mapping[header] for p in profiles_newest_first if header in p.mapping), None
        )
        if exact_profile_match is not None:
            suggestions[header] = exact_profile_match
            continue

        close = get_close_matches(header, known_headers.keys(), n=1, cutoff=0.6)
        suggestions[header] = known_headers[close[0]] if close else None

    return suggestions
