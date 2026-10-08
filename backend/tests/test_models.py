"""Model roundtrip tests against in-memory SQLite."""

import uuid

from app.models import Case, Document, ExtractedField, Flag, ReviewTask
from app.models.enums import CaseStatus, DocType, FlagType, OcrStatus, Severity


def test_case_with_documents_and_flags_roundtrip(db_session) -> None:
    case = Case(
        asset_name="Plot 42, Riverside Estate",
        asset_type="real_estate",
        jurisdiction="IN-KA",
        status=CaseStatus.PROCESSING,
    )
    doc = Document(
        case=case,
        doc_type=DocType.TITLE_DEED,
        original_filename="title_deed.pdf",
        file_path="storage/case1/title_deed.pdf",
        page_count=3,
        ocr_status=OcrStatus.DONE,
    )
    field = ExtractedField(
        document=doc,
        field_name="owner_name",
        value="Ravi Kumar",
        confidence=0.92,
        source_page=1,
        source_snippet="Owner: Ravi Kumar",
    )
    flag = Flag(
        case=case,
        severity=Severity.HIGH,
        flag_type=FlagType.MISMATCH,
        description="Owner name differs between title deed and SPV papers",
        related_fields=[{"document_id": str(doc.id), "field_name": "owner_name"}],
        rule_id="owner_name_mismatch",
    )
    review = ReviewTask(case=case, reason="high severity flag present")
    db_session.add_all([case, doc, field, flag, review])
    db_session.commit()

    stored = db_session.get(Case, case.id)
    assert stored is not None
    assert stored.status_enum == CaseStatus.PROCESSING
    assert len(stored.documents) == 1
    assert stored.documents[0].fields[0].confidence == 0.92
    assert stored.flags[0].severity == Severity.HIGH
    assert stored.review_tasks[0].status == "open"
    assert isinstance(stored.id, uuid.UUID)
    # cascade delete
    db_session.delete(stored)
    db_session.commit()
    assert db_session.get(Document, doc.id) is None
    assert db_session.get(ExtractedField, field.id) is None
