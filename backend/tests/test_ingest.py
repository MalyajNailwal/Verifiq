"""IngestNode tests using plain-text fixtures (no OCR dependency)."""

import pytest

from app.models import Case, Document
from app.models.enums import DocType, OcrStatus
from app.services.ingest import IngestError, ingest_document


@pytest.fixture()
def doc(db_session) -> Document:
    case = Case(asset_name="Plot 42", asset_type="real_estate")
    document = Document(
        case=case,
        doc_type=DocType.TITLE_DEED,
        original_filename="deed.txt",
        file_path="cases/x/deed.txt",
    )
    db_session.add_all([case, document])
    db_session.commit()
    return document


def test_text_ingestion_pages(db_session, doc) -> None:
    payload = (
        "TITLE DEED page one text with plenty of characters here."
        "\fPage two also has enough text to be considered readable."
    )
    result = ingest_document(db_session, doc, file_bytes=payload.encode())

    assert result.ocr_status == OcrStatus.DONE
    assert result.page_count == 2
    pages = sorted(result.pages, key=lambda p: p.page_number)
    assert pages[0].page_number == 1
    assert "TITLE DEED" in pages[0].text
    assert not pages[0].needs_vision


def test_sparse_page_flagged_needs_vision(db_session, doc) -> None:
    result = ingest_document(
        db_session,
        doc,
        file_bytes=b"dense first page with plenty of real content written here\f short",
    )
    pages = sorted(result.pages, key=lambda p: p.page_number)
    assert pages[0].needs_vision is False
    assert pages[1].needs_vision is True  # 'short' < SPARSE_PAGE_CHARS
    assert pages[1].char_count == 5


def test_ingestion_idempotent_replaces_pages(db_session, doc) -> None:
    ingest_document(db_session, doc, file_bytes=b"first version with lots of text")
    first_ids = {p.id for p in doc.pages}
    ingest_document(db_session, doc, file_bytes=b"second version with lots of text")
    assert doc.page_count == 1
    assert all(p.id not in first_ids for p in doc.pages)


def test_unsupported_file_fails_gracefully(db_session) -> None:
    case = Case(asset_name="X", asset_type="real_estate")
    scanned = Document(
        case=case,
        doc_type=DocType.OTHER,
        original_filename="scan.jpg",
        file_path="cases/x/scan.jpg",
    )
    db_session.add_all([case, scanned])
    db_session.commit()
    with pytest.raises(IngestError):
        ingest_document(db_session, scanned, file_bytes=b"binary")
    assert scanned.ocr_status == OcrStatus.FAILED
    assert "no text extractor" in scanned.ocr_error


def test_pages_payload_shape(db_session, doc) -> None:
    ingest_document(db_session, doc, file_bytes=b"hello page text")
    payload = [
        {"page_number": p.page_number, "text": p.text, "needs_vision": p.needs_vision}
        for p in doc.pages
    ]
    assert payload[0]["page_number"] == 1
    assert isinstance(payload[0]["needs_vision"], bool)
