"""Flag model: cross-check/checklist findings attached to a case."""

from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Flag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flags"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    flag_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # list of {document_id, field_name} references involved in this flag
    related_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # rule name that produced it, e.g. "area_mismatch" — aids testing/debugging
    rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 0.0-1.0 determinism score: rules=1.0, LLM-derived lower (reserved)
    rule_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    resolved: Mapped[bool] = mapped_column(default=False, nullable=False)

    case: Mapped["Case"] = relationship(back_populates="flags")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Flag severity={self.severity} type={self.flag_type}>"
