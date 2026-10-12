"""RouterNode tests — conditional human-review routing."""

import pytest

from app.core.config import Settings
from app.models import Case, Document, ExtractedField, Flag, ReviewTask
from app.models.enums import CaseStatus, DocType, FlagType, ReviewStatus, Severity
from app.services.router_node import route_case


@pytest.fixture()
def settings() -> Settings:
    return Settings(DATABASE_URL="sqlite://", LLM_PROVIDER="mock")  # type: ignore[call-arg]


def _case(db_session, *, flags=None, low_conf: bool = False, status=CaseStatus.PROCESSING) -> Case:
    case = Case(asset_name="Plot 42", asset_type="real_estate", status=status)
    db_session.add(case)
    db_session.flush()
    doc = Document(
        case=case, doc_type=DocType.TITLE_DEED, original_filename="d.txt", file_path="x/d.txt"
    )
    db_session.add(doc)
    db_session.flush()
    conf = 0.4 if low_conf else 0.95
    db_session.add(
        ExtractedField(
            document_id=doc.id,
            field_name="owner_name",
            value='"Ravi"',
            confidence=conf,
            source_page=1,
            extraction_reason="ok",
        )
    )
    for sev, ftype in flags or []:
        db_session.add(
            Flag(case_id=case.id, severity=sev, flag_type=ftype, description="test", rule_id="t")
        )
    db_session.add(
        ReviewTask(case_id=case.id, reason="from earlier run", status=ReviewStatus.APPROVED)
    )
    db_session.commit()
    return case


def test_clean_case_completes(db_session, settings) -> None:
    case = _case(db_session)
    assert route_case(db_session, case, settings) == CaseStatus.COMPLETED


def test_high_flag_routes_to_review(db_session, settings) -> None:
    case = _case(db_session, flags=[(Severity.HIGH, FlagType.MISMATCH)])
    status = route_case(db_session, case, settings)
    assert status == CaseStatus.NEEDS_REVIEW
    tasks = (
        db_session.query(ReviewTask)
        .filter(ReviewTask.case_id == case.id, ReviewTask.status == ReviewStatus.OPEN)
        .all()
    )
    assert len(tasks) == 1
    assert "high-severity" in tasks[0].reason


def test_low_confidence_routes_to_review(db_session, settings) -> None:
    case = _case(db_session, low_conf=True)
    assert route_case(db_session, case, settings) == CaseStatus.NEEDS_REVIEW
    task = (
        db_session.query(ReviewTask)
        .filter(ReviewTask.case_id == case.id, ReviewTask.status == ReviewStatus.OPEN)
        .one()
    )
    assert "low-confidence" in task.reason


def test_rejected_stays_rejected(db_session, settings) -> None:
    case = _case(db_session, flags=[(Severity.HIGH, FlagType.MISMATCH)], status=CaseStatus.REJECTED)
    assert route_case(db_session, case, settings) == CaseStatus.REJECTED


def test_no_duplicate_review_tasks(db_session, settings) -> None:
    case = _case(db_session, flags=[(Severity.HIGH, FlagType.MISMATCH)])
    route_case(db_session, case, settings)
    route_case(db_session, case, settings)
    open_count = (
        db_session.query(ReviewTask)
        .filter(ReviewTask.case_id == case.id, ReviewTask.status == ReviewStatus.OPEN)
        .count()
    )
    assert open_count == 1
