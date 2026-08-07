"""loguru file/console logging plus the DB-backed business event log writer.

Two coordinated layers, per spec:
- loguru -> rotating JSON file under gitignored /logs, for system-level
  crashes/startup errors a developer would tail during debugging. TINs and
  addresses are masked before they ever reach this sink.
- `log_event` -> `event_logs` table, for business-level events an
  accounting user needs to see and act on (mismatches, dupes, validation
  warnings). Always carries a plain-language `message` and a
  developer-only `technical_detail`.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.core.models import EventCategory, EventLog, EventSeverity

_configured = False


def configure_logging() -> None:
    """Idempotently point loguru at a rotating JSON file under LOG_DIR."""
    global _configured
    if _configured:
        return
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(
        settings.log_dir / "app.jsonl",
        rotation="10 MB",
        retention="90 days",
        serialize=True,
        level="DEBUG",
        enqueue=True,
    )
    _configured = True


def log_event(
    session: Session,
    *,
    category: EventCategory,
    severity: EventSeverity,
    message: str,
    technical_detail: str | None = None,
    batch_id: int | None = None,
    certificate_id: int | None = None,
    transaction_id: int | None = None,
) -> EventLog:
    """Insert one append-only `event_logs` row and mirror a short line to loguru.

    Full detail (including raw TIN/address) is fine in `technical_detail`
    since `event_logs` is access-controlled at the DB level; the console/
    file mirror only gets the plain-language `message`, never the
    technical detail, keeping PII out of local log files.
    """
    event = EventLog(
        category=category,
        severity=severity,
        message=message,
        technical_detail=technical_detail,
        batch_id=batch_id,
        certificate_id=certificate_id,
        transaction_id=transaction_id,
    )
    session.add(event)
    session.flush()

    log_fn = {
        EventSeverity.INFO: logger.info,
        EventSeverity.WARNING: logger.warning,
        EventSeverity.ERROR: logger.error,
    }[severity]
    log_fn("[{}] {}", category.value, message)
    return event


def resolve_event(
    session: Session, event: EventLog, resolved_by: str, resolution_note: str | None
) -> None:
    """Record a resolution on `event`, once.

    `event_logs` is append-only for its core fields (category, severity,
    message, technical_detail, created_at never change once written); the
    resolved_* columns exist specifically to be filled in exactly once, so
    this is a no-op if the event already has a resolution — never lets the
    UI overwrite or clear an existing resolution.
    """
    if event.resolved_at is not None:
        return
    event.resolved_by = resolved_by
    event.resolved_at = datetime.now(UTC).replace(
        tzinfo=None
    )  # naive, matching other DateTime columns
    event.resolution_note = resolution_note


def search_events(
    session: Session,
    *,
    category: EventCategory | None = None,
    severity: EventSeverity | None = None,
    unresolved_only: bool = False,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[EventLog], int]:
    """Combinable filters over `event_logs`, newest first, paginated."""
    query = session.query(EventLog)
    if category is not None:
        query = query.filter(EventLog.category == category)
    if severity is not None:
        query = query.filter(EventLog.severity == severity)
    if unresolved_only:
        query = query.filter(EventLog.resolved_at.is_(None))

    total_count = query.count()
    items = (
        query.order_by(EventLog.created_at.desc(), EventLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total_count
