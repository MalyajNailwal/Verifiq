"""ExtractedField model: every LLM-extracted value with confidence + source reference."""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExtractedField(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extracted_fields"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # JSON-encoded value (scalars or {"value": .., "unit": ..} composites).
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "not_found" | "low_confidence" | "ok" | reviewer-set reason
    extraction_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # set by human review when a field is corrected
    edited_by_reviewer: Mapped[bool] = mapped_column(default=False, nullable=False)

    document: Mapped["Document"] = relationship(  # noqa: F821
        back_populates="fields"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ExtractedField field={self.field_name} conf={self.confidence:.2f} "
            f"page={self.source_page}>"
        )
