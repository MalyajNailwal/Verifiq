"""ReviewTask model: human-in-the-loop queue entries."""

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReviewTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_tasks"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # machine-readable triggers: {"low_confidence_fields": [...], "high_flags": [...]}
    triggers: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # type: ignore[valid-type]
    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="review_tasks")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReviewTask case={self.case_id!s} status={self.status}>"
