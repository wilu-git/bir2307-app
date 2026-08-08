"""SQLAlchemy ORM models for the BIR 2307 generator.

Schema follows the project spec exactly (payees, payors, atc_codes,
import_batches, transactions, certificates, certificate_transactions,
status_log, event_logs). `event_logs` and `status_log` are append-only by
convention — no code path in this app should ever UPDATE or DELETE a row in
either table; resolution is recorded as new column values on the same
never-deleted row, not as a separate mutable history.
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaxType(str, enum.Enum):
    VAT = "VAT"
    NONVAT = "NONVAT"


class CertificateStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    FORWARDED = "forwarded"
    COMPLETED_SIGNED = "completed_signed"
    VOID = "void"


class EventCategory(str, enum.Enum):
    FILE_PARSE = "FILE_PARSE"
    ROW_VALIDATION = "ROW_VALIDATION"
    TIN_FORMAT = "TIN_FORMAT"
    DUPLICATE_REFERENCE = "DUPLICATE_REFERENCE"
    COMPUTATION_MISMATCH = "COMPUTATION_MISMATCH"
    ATC_RATE_UNKNOWN = "ATC_RATE_UNKNOWN"
    PDF_GENERATION = "PDF_GENERATION"
    STATUS_TRANSITION = "STATUS_TRANSITION"
    SYSTEM = "SYSTEM"


class EventSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Payee(Base):
    __tablename__ = "payees"

    id: Mapped[int] = mapped_column(primary_key=True)
    tin: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    registered_name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text, default=None)
    zip_code: Mapped[str | None] = mapped_column(String(10), default=None)
    tax_type: Mapped[TaxType] = mapped_column(Enum(TaxType))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="payee")
    certificates: Mapped[list["Certificate"]] = relationship(back_populates="payee")


class Payor(Base):
    __tablename__ = "payors"

    id: Mapped[int] = mapped_column(primary_key=True)
    tin: Mapped[str] = mapped_column(String(20))
    registered_name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text, default=None)
    zip_code: Mapped[str | None] = mapped_column(String(10), default=None)


class AtcCode(Base):
    __tablename__ = "atc_codes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    default_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    income_type: Mapped[str | None] = mapped_column(String(255), default=None)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    row_count: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="batch")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"))
    payee_id: Mapped[int] = mapped_column(ForeignKey("payees.id"), index=True)
    payor_id: Mapped[int] = mapped_column(ForeignKey("payors.id"))
    reference_no: Mapped[str] = mapped_column(String(100), index=True)
    atc_code: Mapped[str] = mapped_column(ForeignKey("atc_codes.code"))
    total_billing: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax_base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    rate_applied: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    tax_withheld: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2))
<<<<<<< Updated upstream
    assigned_to: Mapped[str | None] = mapped_column(String(255), default=None)
    date_accomplished: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    remarks: Mapped[str | None] = mapped_column(Text, default=None)
=======
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
>>>>>>> Stashed changes
    overflow_notes: Mapped[str | None] = mapped_column(Text, default=None)
    raw_row_json: Mapped[str | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    batch: Mapped["ImportBatch"] = relationship(back_populates="transactions")
    payee: Mapped["Payee"] = relationship(back_populates="transactions")
    payor: Mapped["Payor"] = relationship()


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    payee_id: Mapped[int] = mapped_column(ForeignKey("payees.id"), index=True)
    payor_id: Mapped[int] = mapped_column(ForeignKey("payors.id"))
    period_start: Mapped[datetime] = mapped_column(DateTime)
    period_end: Mapped[datetime] = mapped_column(DateTime)
    total_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_tax_withheld: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus), default=CertificateStatus.DRAFT, index=True
    )
    pdf_unsigned_path: Mapped[str | None] = mapped_column(String(500), default=None)
    pdf_signed_path: Mapped[str | None] = mapped_column(String(500), default=None)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    payee: Mapped["Payee"] = relationship(back_populates="certificates")
    payor: Mapped["Payor"] = relationship()
    transaction_links: Mapped[list["CertificateTransaction"]] = relationship(
        back_populates="certificate"
    )


class CertificateTransaction(Base):
    __tablename__ = "certificate_transactions"

    certificate_id: Mapped[int] = mapped_column(ForeignKey("certificates.id"), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), primary_key=True)

    certificate: Mapped["Certificate"] = relationship(back_populates="transaction_links")
    transaction: Mapped["Transaction"] = relationship()

    __table_args__ = (UniqueConstraint("certificate_id", "transaction_id"),)


class StatusLog(Base):
    __tablename__ = "status_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    certificate_id: Mapped[int] = mapped_column(ForeignKey("certificates.id"))
    old_status: Mapped[str | None] = mapped_column(String(30), default=None)
    new_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, default=None)


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), default=None)
    certificate_id: Mapped[int | None] = mapped_column(ForeignKey("certificates.id"), default=None)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), default=None)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory))
    severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity))
    message: Mapped[str] = mapped_column(Text)
    technical_detail: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    resolution_note: Mapped[str | None] = mapped_column(Text, default=None)


class ImportColumnMapping(Base):
    """A saved, reusable Excel column mapping profile.

    `mapping` is the same shape as `import_excel.COLUMN_MAP`: normalized
    source header -> internal field name. Stored whole as JSON (mirrors the
    `raw_row_json` precedent) since a profile is always read/written as one
    unit, never queried by individual header.
    """

    __tablename__ = "import_column_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), default=None)
    mapping: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
