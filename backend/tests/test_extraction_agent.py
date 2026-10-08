"""ExtractionAgent tests with the deterministic MockLLMClient (no network)."""

import json

import pytest

from app.core.config import Settings
from app.core.llm import MockLLMClient
from app.models import Case, Document, ExtractedField, LLMCallLog
from app.models.enums import DocType
from app.services.extraction import ExtractionError, extract_document
from app.services.ingest import ingest_document

CANNED_OK = json.dumps(
    {
        "fields": [
            {
                "field_name": "owner_name",
                "value": "Ananya Deshpande",
                "confidence": 0.97,
                "source_page": 1,
                "source_snippet": "Owner: Mrs. Ananya Deshpande",
                "reason": "ok",
            },
            {
                "field_name": "area",
                "value": {"value": 4200, "unit": "sq ft"},
                "confidence": 0.95,
                "source_page": 1,
                "source_snippet": "Total area: 4,200 sq ft",
                "reason": "ok",
            },
            {
                "field_name": "owner_name",
                "value": "duplicate ignored",
                "confidence": 0.5,
                "source_page": 1,
                "source_snippet": None,
                "reason": "ambiguous",
            },
            {
                "field_name": "not_a_real_field",
                "value": "x",
                "confidence": 0.9,
                "source_page": 1,
                "source_snippet": None,
                "reason": "ok",
            },
        ],
        "document_summary": "Title deed.",
        "is_readable": True,
    }
)


@pytest.fixture()
def settings() -> Settings:
    return Settings(DATABASE_URL="sqlite://", LLM_PROVIDER="mock")  # type: ignore[call-arg]


@pytest.fixture()
def ingested_doc(db_session) -> Document:
    case = Case(asset_name="Plot 42", asset_type="real_estate")
    doc = Document(
        case=case,
        doc_type=DocType.TITLE_DEED,
        original_filename="deed.txt",
        file_path="cases/x/deed.txt",
    )
    db_session.add_all([case, doc])
    db_session.commit()
    ingest_document(
        db_session,
        doc,
        file_bytes=b"Owner: Mrs. Ananya Deshpande\nTotal area: 4,200 sq ft",
    )
    return doc


def test_extract_persists_fields_with_sources(db_session, ingested_doc, settings) -> None:
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = CANNED_OK

    fields = extract_document(db_session, ingested_doc, llm, settings)

    by_name = {f.field_name: f for f in fields}
    # 14 known fields always present; unknown filtered; duplicate resolved to first.
    assert len(fields) == 14
    owner = by_name["owner_name"]
    assert json.loads(owner.value) == "Ananya Deshpande"
    assert owner.confidence == 0.97
    assert owner.source_page == 1
    assert owner.source_snippet == "Owner: Mrs. Ananya Deshpande"
    area = by_name["area"]
    assert json.loads(area.value) == {"value": 4200, "unit": "sq ft"}
    # absent fields explicitly null + not_found (constraint #5)
    assert by_name["valuation_amount"].value is None
    assert by_name["valuation_amount"].extraction_reason == "not_found"


def test_missing_fields_backfilled_as_not_found(db_session, ingested_doc, settings) -> None:
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = json.dumps({"fields": [], "is_readable": True})
    fields = extract_document(db_session, ingested_doc, llm, settings)
    assert len(fields) == 14
    assert all(f.extraction_reason == "not_found" and f.value is None for f in fields)


def test_prompt_template_rendered_with_doc_context(db_session, ingested_doc, settings) -> None:
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = CANNED_OK
    extract_document(db_session, ingested_doc, llm, settings)
    prompt = llm.calls[0]
    assert "TITLE_DEED" in prompt.replace("title_deed", "TITLE_DEED") or "title_deed" in prompt
    assert "Owner: Mrs. Ananya Deshpande" in prompt
    assert "PAGE 1" in prompt
    assert "NEVER guess" in prompt


def test_low_confidence_fields_identifiable(db_session, ingested_doc, settings) -> None:
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = json.dumps(
        {
            "fields": [
                {
                    "field_name": "owner_name",
                    "value": "A D",
                    "confidence": 0.4,
                    "source_page": 1,
                    "source_snippet": "A D",
                    "reason": "ambiguous",
                }
            ],
            "is_readable": True,
        }
    )
    fields = extract_document(db_session, ingested_doc, llm, settings)
    low = [f for f in fields if f.confidence < settings.confidence_threshold]
    assert [f.field_name for f in low] == ["owner_name"]


def test_llm_call_logged_with_metadata(db_session, ingested_doc, settings) -> None:
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = CANNED_OK
    extract_document(db_session, ingested_doc, llm, settings)
    logs = db_session.query(LLMCallLog).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.provider == "mock"
    assert log.prompt_name == "extraction"
    assert log.prompt_version == "v1"
    assert log.status == "ok"
    assert log.case_id == str(ingested_doc.case_id)


def test_invalid_llm_output_raises_and_no_fields(db_session, ingested_doc, settings) -> None:
    llm = MockLLMClient(max_retries=0)
    llm.canned["DOCUMENT TEXT"] = "not json"
    with pytest.raises(ExtractionError):
        extract_document(db_session, ingested_doc, llm, settings)
    assert db_session.query(ExtractedField).count() == 0
    # failure is audited
    assert db_session.query(LLMCallLog).filter_by(status="error").count() == 1
