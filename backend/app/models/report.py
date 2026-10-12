"""Report model: final investor-ready verification report per case."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    risk_rating: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # machine-readable checklist: [{doc_type, required, present, status, note}]
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # rule-based score components, kept for auditability
    score_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # SHA-256 of the canonical report JSON (anchored on-chain in a later phase)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Phase 6: on-chain anchoring of report_hash on Polygon Amoy testnet
    anchor_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    anchor_tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    anchor_block_number: Mapped[int | None] = mapped_column(nullable=True)
    anchored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="report")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report case={self.case_id!s} rating={self.risk_rating}>"
