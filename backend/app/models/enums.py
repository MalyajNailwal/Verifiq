"""Shared enumerations for models and schemas (stored as strings in DB for portability)."""

from enum import StrEnum


class CaseStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    REJECTED = "rejected"


class DocType(StrEnum):
    TITLE_DEED = "title_deed"
    VALUATION_REPORT = "valuation_report"
    LEGAL_OPINION = "legal_opinion"
    SPV_PAPERS = "spv_papers"
    OTHER = "other"


class OcrStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FlagType(StrEnum):
    MISMATCH = "mismatch"
    MISSING_DOC = "missing_doc"
    EXPIRED_DOC = "expired_doc"
    LOW_CONFIDENCE = "low_confidence"
    OTHER = "other"


class RiskRating(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
