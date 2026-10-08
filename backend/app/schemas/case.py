"""Case, Document, ExtractedField API schemas (Pydantic v2)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import CaseStatus, DocType, OcrStatus


class CaseCreate(BaseModel):
    asset_name: str = Field(min_length=1, max_length=255, examples=["Plot 42, Riverside Estate"])
    asset_type: str = Field(default="real_estate", max_length=64)
    jurisdiction: str | None = Field(default=None, max_length=64, examples=["IN-KA"])


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_name: str
    asset_type: str
    jurisdiction: str | None
    status: CaseStatus
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    doc_type: DocType
    original_filename: str
    page_count: int | None
    ocr_status: OcrStatus
    sha256: str | None


class ExtractedFieldOut(BaseModel):
    """API view of an extracted field — always carries confidence + source reference."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    field_name: str
    value: Any | None
    normalized_value: Any | None
    confidence: float
    source_page: int | None
    source_snippet: str | None
    extraction_reason: str | None
    edited_by_reviewer: bool


class CaseDetail(CaseOut):
    documents: list[DocumentOut] = []
    fields: list[ExtractedFieldOut] = []
