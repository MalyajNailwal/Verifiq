"""Report API schema."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import RiskRating


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    risk_rating: RiskRating
    summary: str
    checklist: list[dict[str, Any]] | None
    score_details: dict[str, Any] | None
    report_hash: str
    pdf_path: str | None
    generated_at: datetime
