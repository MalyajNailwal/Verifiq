"""Review queue endpoints — human-in-the-loop resolution."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Case, ExtractedField, Flag, ReviewTask
from app.models.enums import CaseStatus, ReviewStatus
from app.schemas import ReviewResolveRequest, ReviewTaskOut
from app.services.router_node import route_case

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review-tasks", tags=["review"])


@router.get("", response_model=list[ReviewTaskOut])
def list_tasks(status: str | None = None, db: Session = Depends(get_db)) -> list[ReviewTask]:
    query = db.query(ReviewTask).order_by(ReviewTask.created_at.desc())
    if status:
        try:
            query = query.filter(ReviewTask.status == ReviewStatus(status))
        except ValueError as exc:
            raise HTTPException(400, f"invalid status '{status}'") from exc
    return query.all()


@router.post("/{task_id}/resolve", response_model=ReviewTaskOut)
def resolve_task(
    task_id: str,
    payload: ReviewResolveRequest,
    db: Session = Depends(get_db),
) -> ReviewTask:
    import uuid

    try:
        tid = uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid task id") from exc
    task = db.get(ReviewTask, tid)
    if task is None:
        raise HTTPException(404, f"review task {task_id} not found")
    if task.status not in (ReviewStatus.OPEN, ReviewStatus.IN_PROGRESS):
        raise HTTPException(409, f"task already resolved ({task.status})")
    if payload.decision not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
        raise HTTPException(400, "decision must be approved or rejected")

    # Apply reviewer field corrections before routing.
    for field_id, edit in (payload.field_edits or {}).items():
        field = db.get(ExtractedField, _uuid(field_id))
        if field is None:
            raise HTTPException(404, f"field {field_id} not found")
        if "value" in edit:
            field.value = json.dumps(edit["value"], ensure_ascii=False)
            field.edited_by_reviewer = True
            field.extraction_reason = "reviewer_corrected"
        if "confidence" in edit:
            field.confidence = float(edit["confidence"])

    task.status = payload.decision
    task.reviewer_notes = payload.reviewer_notes
    task.decided_by = payload.decided_by

    # Resolve flags the reviewer is signing off on.
    if payload.decision == ReviewStatus.APPROVED:
        db.query(Flag).filter(Flag.case_id == task.case_id).update(
            {"resolved": True}, synchronize_session=False
        )

    case = db.get(Case, task.case_id)
    if case is not None:
        if payload.decision == ReviewStatus.REJECTED:
            case.status = CaseStatus.REJECTED
        else:
            route_case(db, case, _settings(db))
    db.commit()
    logger.info("review_resolved task=%s decision=%s", task.id, payload.decision)
    return task


def _uuid(value: str):
    import uuid

    return uuid.UUID(value)


def _settings(db: Session):
    from app.core.config import get_settings

    return get_settings()
