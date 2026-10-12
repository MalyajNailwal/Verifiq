"""RouterNode — conditional transition after all agents have run.

Rules (constraint #3):
- any unresolved HIGH-severity flag  → needs_review
- any field confidence < threshold   → needs_review
- else                               → completed
- reviewer-rejected cases stay rejected
"""

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Case, ExtractedField, Flag, ReviewTask
from app.models.enums import CaseStatus, ReviewStatus, Severity

logger = logging.getLogger(__name__)


def route_case(db: Session, case: Case, settings: Settings) -> str:
    """Apply human-review routing; returns the final status string."""
    if case.status == CaseStatus.REJECTED:
        logger.info("router case_id=%s stays rejected", case.id)
        return case.status

    doc_ids = {d.id for d in case.documents}

    unresolved = db.query(Flag).filter(Flag.case_id == case.id, Flag.resolved.is_(False)).all()
    has_high = any(f.severity == Severity.HIGH for f in unresolved)

    low_conf_ids = (
        [
            f.id
            for f in db.query(ExtractedField).filter(ExtractedField.document_id.in_(doc_ids)).all()
            if f.confidence < settings.confidence_threshold and f.extraction_reason != "not_found"
        ]
        if doc_ids
        else []
    )

    if has_high or low_conf_ids:
        reasons = []
        if has_high:
            reasons.append("high-severity flag present")
        if low_conf_ids:
            reasons.append(f"{len(low_conf_ids)} low-confidence field(s)")
        existing = (
            db.query(ReviewTask)
            .filter(
                ReviewTask.case_id == case.id,
                ReviewTask.status.in_([ReviewStatus.OPEN, ReviewStatus.IN_PROGRESS]),
            )
            .all()
        )
        if not existing:
            db.add(
                ReviewTask(
                    case_id=case.id,
                    reason="; ".join(reasons),
                    triggers={
                        "high_flags": [
                            str(f.id) for f in unresolved if f.severity == Severity.HIGH
                        ],
                        "low_confidence_fields": [str(i) for i in low_conf_ids],
                    },
                    status=ReviewStatus.OPEN,
                )
            )
        case.status = CaseStatus.NEEDS_REVIEW
        logger.info("router case_id=%s -> needs_review (%s)", case.id, "; ".join(reasons))
    else:
        open_tasks = (
            db.query(ReviewTask)
            .filter(
                ReviewTask.case_id == case.id,
                ReviewTask.status.in_([ReviewStatus.OPEN, ReviewStatus.IN_PROGRESS]),
            )
            .count()
        )
        if open_tasks == 0:
            case.status = CaseStatus.COMPLETED
            logger.info("router case_id=%s -> completed", case.id)
    db.commit()
    return case.status
