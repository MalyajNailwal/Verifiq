"""Document and per-page OCR text models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import DocType, OcrStatus


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocType.OTHER, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_status: Mapped[str] = mapped_column(String(16), nullable=False, default=OcrStatus.PENDING)
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )

    case: Mapped["Case"] = relationship(back_populates="documents")  # noqa: F821
    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )
    fields: Mapped[list["ExtractedField"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Document id={self.id!s} type={self.doc_type} file={self.original_filename!r}>"


class DocumentPage(UUIDPrimaryKeyMixin, Base):
    """One row per page: raw extracted text + a flag for vision fallback need."""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_doc_page"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_vision: Mapped[bool] = mapped_column(default=False, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="pages")  # noqa: F821
