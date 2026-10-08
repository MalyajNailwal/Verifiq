"""Case aggregate root."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CaseStatus


class Case(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cases"

    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, default="real_estate")
    jurisdiction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CaseStatus.UPLOADED, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    flags: Mapped[list["Flag"]] = relationship(  # noqa: F821
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )
    report: Mapped["Report | None"] = relationship(  # noqa: F821
        back_populates="case", cascade="all, delete-orphan", lazy="selectin", uselist=False
    )
    review_tasks: Mapped[list["ReviewTask"]] = relationship(  # noqa: F821
        back_populates="case", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def status_enum(self) -> CaseStatus:
        return CaseStatus(self.status)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Case id={self.id!s} asset={self.asset_name!r} status={self.status}>"
