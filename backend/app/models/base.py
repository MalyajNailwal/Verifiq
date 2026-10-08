"""Declarative base and shared mixins."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Timezone-aware UTC now (never use naive datetimes)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class UUIDPrimaryKeyMixin:
    """UUID primary key, generated in Python so it exists before flush."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, sort_order=-100
    )


class TimestampMixin:
    """created_at/updated_at columns, timezone-aware."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, onupdate=utcnow, nullable=True
    )


class CaseIdMixin:
    """Foreign key to a case, indexed (used by child tables)."""

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
