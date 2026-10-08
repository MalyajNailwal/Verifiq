"""Pipeline service tests (Phase 2 scope: ingest + extraction)."""

import json
import uuid

import pytest

from app.core.config import Settings
from app.core.llm import MockLLMClient
from app.models import Case, Document, ExtractedField
from app.models.enums import CaseStatus, DocType, OcrStatus
from app.services.pipeline import run_case_pipeline
from app.services.storage import LocalStorage

CANNED = json.dumps(
    {
        "fields": [
            {
                "field_name": "owner_name",
                "value": "Ananya Deshpande",
                "confidence": 0.97,
                "source_page": 1,
                "source_snippet": "Owner: Mrs. Ananya Deshpande",
                "reason": "ok",
            }
        ],
        "is_readable": True,
    }
)


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        DATABASE_URL="sqlite://",
        LLM_PROVIDER="mock",
        STORAGE_DIR=str(tmp_path / "storage"),
    )


def _case_with_file(db_session, settings: Settings, filename: str, content: bytes) -> Case:
    case = Case(asset_name="Plot 42", asset_type="real_estate")
    db_session.add(case)
    db_session.commit()
    storage = LocalStorage(settings.storage_dir)
    stored = storage.save_bytes(case.id, "title_deed", filename, content)
    doc = Document(
        case=case,
        doc_type=DocType.TITLE_DEED,
        original_filename=filename,
        file_path=stored["path"],
        sha256=stored["sha256"],
    )
    db_session.add(doc)
    db_session.commit()
    return case


def test_pipeline_happy_path(db_session, settings) -> None:
    case = _case_with_file(
        db_session,
        settings,
        "deed.txt",
        b"Owner: Mrs. Ananya Deshpande\nTotal area: 4,200 sq ft",
    )
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = CANNED

    result = run_case_pipeline(db_session, case.id, llm, settings)

    assert result.status == CaseStatus.PROCESSING
    assert case.status == CaseStatus.PROCESSING
    doc = case.documents[0]
    assert doc.ocr_status == OcrStatus.DONE
    assert doc.page_count == 1
    fields = db_session.query(ExtractedField).filter_by(document_id=doc.id).all()
    assert len(fields) == 14  # full schema backfilled
    owner = next(f for f in fields if f.field_name == "owner_name")
    assert json.loads(owner.value) == "Ananya Deshpande"


def test_pipeline_skips_already_processed(db_session, settings) -> None:
    case = _case_with_file(db_session, settings, "deed.txt", b"some deed text content")
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = CANNED
    run_case_pipeline(db_session, case.id, llm, settings)
    calls_after_first = len(llm.calls)

    run_case_pipeline(db_session, case.id, llm, settings)  # re-run
    assert len(llm.calls) == calls_after_first  # no new LLM calls


def test_pipeline_isolates_document_errors(db_session, settings) -> None:
    # .txt ingests fine; .jpg extraction path fails but must not crash the run.
    case = _case_with_file(db_session, settings, "deed.txt", b"deed text here")
    storage = LocalStorage(settings.storage_dir)
    stored = storage.save_bytes(case.id, "other", "scan.jpg", b"jpg-bytes")
    bad = Document(
        case=case,
        doc_type=DocType.OTHER,
        original_filename="scan.jpg",
        file_path=stored["path"],
    )
    db_session.add(bad)
    db_session.commit()

    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = CANNED
    result = run_case_pipeline(db_session, case.id, llm, settings)

    assert len(result.documents) == 2
    good = next(r for r in result.documents if r.extracted)
    bad_result = next(r for r in result.documents if not r.extracted)
    assert good.error is None
    assert bad_result.error is not None


def test_pipeline_unknown_case_raises(db_session, settings) -> None:
    llm = MockLLMClient()
    with pytest.raises(ValueError, match="not found"):
        run_case_pipeline(db_session, uuid.uuid4(), llm, settings)
