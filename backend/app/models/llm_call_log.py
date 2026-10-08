"""LLMCallLog: audit row for every LLM call (prompt version, tokens, latency)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, utcnow


class LLMCallLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "llm_call_logs"

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # identifier of the prompt template used, e.g. "extraction/v1"
    prompt_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # "complete" or "complete_structured"; structured rows record retries
    call_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<LLMCallLog provider={self.provider} status={self.status} "
            f"latency_ms={self.latency_ms}>"
        )
