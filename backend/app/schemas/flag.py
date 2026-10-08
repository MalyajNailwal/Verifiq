"""Flag and ReviewTask API schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import FlagType, ReviewStatus, Severity


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    severity: Severity
    flag_type: FlagType
    description: str
    related_fields: list[dict[str, Any]] | None
    rule_id: str | None
    rule_confidence: float
    resolved: bool


class ReviewTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    reason: str
    triggers: dict[str, Any] | None
    assigned_to: str | None
    status: ReviewStatus
    reviewer_notes: str | None
    created_at: datetime


class ReviewResolveRequest(BaseModel):
    decision: ReviewStatus = Field(description="approved or rejected")
    reviewer_notes: str | None = None
    decided_by: str | None = Field(default=None, max_length=128)

    # Optional field corrections applied before approval: {field_id: {value, confidence}}
    field_edits: dict[str, dict[str, Any]] | None = None
