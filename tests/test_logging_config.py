from app.core.logging_config import log_event, resolve_event, search_events
from app.core.models import EventCategory, EventSeverity


def test_resolve_event_sets_resolution_fields(session):
    event = log_event(
        session,
        category=EventCategory.TIN_FORMAT,
        severity=EventSeverity.WARNING,
        message="Malformed TIN.",
    )
    session.commit()

    resolve_event(session, event, "test_user", "Confirmed with vendor.")
    session.commit()

    assert event.resolved_by == "test_user"
    assert event.resolved_at is not None
    assert event.resolution_note == "Confirmed with vendor."


def test_resolve_event_is_a_noop_if_already_resolved(session):
    event = log_event(
        session,
        category=EventCategory.TIN_FORMAT,
        severity=EventSeverity.WARNING,
        message="Malformed TIN.",
    )
    session.commit()

    resolve_event(session, event, "first_user", "First note.")
    session.commit()
    first_resolved_at = event.resolved_at

    resolve_event(session, event, "second_user", "Attempted overwrite.")
    session.commit()

    assert event.resolved_by == "first_user"
    assert event.resolution_note == "First note."
    assert event.resolved_at == first_resolved_at


def test_log_event_message_never_mutated_by_resolution(session):
    event = log_event(
        session,
        category=EventCategory.COMPUTATION_MISMATCH,
        severity=EventSeverity.WARNING,
        message="Original message.",
        technical_detail="Original detail.",
    )
    session.commit()

    resolve_event(session, event, "test_user", "Resolved.")
    session.commit()

    assert event.message == "Original message."
    assert event.technical_detail == "Original detail."


def test_search_events_filters_by_category(session):
    log_event(
        session, category=EventCategory.TIN_FORMAT, severity=EventSeverity.WARNING, message="a"
    )
    log_event(
        session,
        category=EventCategory.DUPLICATE_REFERENCE,
        severity=EventSeverity.INFO,
        message="b",
    )
    session.commit()

    items, total = search_events(session, category=EventCategory.TIN_FORMAT)
    assert total == 1
    assert items[0].message == "a"


def test_search_events_filters_by_severity(session):
    log_event(session, category=EventCategory.SYSTEM, severity=EventSeverity.ERROR, message="err")
    log_event(session, category=EventCategory.SYSTEM, severity=EventSeverity.INFO, message="info")
    session.commit()

    items, total = search_events(session, severity=EventSeverity.ERROR)
    assert total == 1
    assert items[0].message == "err"


def test_search_events_unresolved_only(session):
    resolved = log_event(
        session,
        category=EventCategory.SYSTEM,
        severity=EventSeverity.WARNING,
        message="resolved one",
    )
    log_event(
        session,
        category=EventCategory.SYSTEM,
        severity=EventSeverity.WARNING,
        message="unresolved one",
    )
    session.commit()
    resolve_event(session, resolved, "test_user", None)
    session.commit()

    items, total = search_events(session, unresolved_only=True)
    assert total == 1
    assert items[0].message == "unresolved one"


def test_search_events_pagination(session):
    for i in range(5):
        log_event(
            session, category=EventCategory.SYSTEM, severity=EventSeverity.INFO, message=f"msg {i}"
        )
    session.commit()

    items, total = search_events(session, page=1, page_size=2)
    assert total == 5
    assert len(items) == 2
