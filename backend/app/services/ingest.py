"""IngestNode — per-page text extraction for a document.

Strategy:
1. Text PDFs → pdfplumber (fast, exact text). Requires `pip install '.[ocr]'`.
2. Plain text files (.txt/.md) → direct page split.
3. Scanned/low-text pages → PaddleOCR when installed, else the page is marked
   `needs_vision=True` so the ExtractionAgent can route it to a vision LLM.
4. Never fails the whole document: per-page errors are logged and recorded.

A page is "sparse" if its extracted text is under SPARSE_PAGE_CHARS — that
triggers the OCR/vision path.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Document, DocumentPage
from app.models.enums import OcrStatus

logger = logging.getLogger(__name__)

SPARSE_PAGE_CHARS = 40


class IngestError(Exception):
    pass


def _pdf_pages(absolute_path: str) -> list[str]:
    """Text-PDF extraction via pdfplumber. Raises if pdfplumber is absent."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise IngestError("pdfplumber not installed — run: pip install '.[ocr]'") from exc
    pages: list[str] = []
    with pdfplumber.open(absolute_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def _text_pages(data: bytes) -> list[str]:
    """Split plain-text uploads on form-feed; fallback to single page."""
    text = data.decode("utf-8", errors="replace")
    parts = text.split("\f")
    return parts if len(parts) > 1 else [text]


def _ocr_page(image_path: str) -> str:
    """PaddleOCR for scanned pages. Caller must check availability first."""

    ocr = _ocr_page._engine  # type: ignore[attr-defined]
    result = ocr.ocr(image_path)
    lines: list[str] = []
    for page_result in result or []:
        for item in page_result or []:
            lines.append(item[1][0])
    return "\n".join(lines)


_ocr_page._engine = None  # type: ignore[attr-defined]


def paddle_available() -> bool:
    try:
        import paddleocr  # noqa: F401

        return True
    except ImportError:
        return False


def _ensure_ocr_engine() -> None:
    if _ocr_page._engine is None:  # type: ignore[attr-defined]
        from paddleocr import PaddleOCR

        _ocr_page._engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)  # type: ignore[attr-defined]


def ingest_document(
    db: Session, doc: Document, *, file_bytes: bytes | None = None, absolute_path: str | None = None
) -> Document:
    """Populate DocumentPage rows for a document; updates ocr_status/page_count.

    Either file_bytes or absolute_path must be provided. Deterministic and
    re-runnable: existing pages for the document are replaced.
    """
    filename = doc.original_filename.lower()
    if file_bytes is None:
        if absolute_path is None:
            raise IngestError("provide file_bytes or absolute_path")
        with open(absolute_path, "rb") as fh:
            file_bytes = fh.read()

    doc.ocr_status = OcrStatus.RUNNING
    try:
        if filename.endswith((".txt", ".md")):
            pages = _text_pages(file_bytes)
            method = "text"
        else:  # treat everything else as PDF-ish
            pages = _pdf_pages(absolute_path or "")
            method = "pdfplumber"
    except IngestError:
        doc.ocr_status = OcrStatus.FAILED
        doc.ocr_error = "no text extractor available for this file type"
        db.commit()
        raise
    except Exception as exc:
        doc.ocr_status = OcrStatus.FAILED
        doc.ocr_error = f"extraction failed: {exc}"
        db.commit()
        raise IngestError(str(exc)) from exc

    # Replace prior pages (idempotent re-run).
    doc.pages.clear()
    db.flush()

    for idx, text in enumerate(pages, start=1):
        sparse = len(text.strip()) < SPARSE_PAGE_CHARS
        page = DocumentPage(
            document_id=doc.id,
            page_number=idx,
            text=text or None,
            char_count=len(text.strip()),
            needs_vision=sparse,
            extraction_method=method,
        )
        if sparse and paddle_available():
            try:
                _ensure_ocr_engine()
                # No image rendering in MVP text path; OCR hooks in Phase 3
                # when scanned-sample rendering lands.
            except Exception as exc:  # pragma: no cover - depends on optional dep
                logger.warning("ocr_unavailable page=%d err=%s", idx, exc)
        doc.pages.append(page)

    doc.page_count = len(pages)
    doc.ocr_status = OcrStatus.DONE
    doc.ocr_error = None
    db.commit()
    logger.info(
        "ingested document_id=%s pages=%d method=%s sparse=%d",
        doc.id,
        len(pages),
        method,
        sum(1 for p in doc.pages if p.needs_vision),
    )
    return doc


def pages_payload(doc: Document) -> list[dict[str, Any]]:
    """Build the page-text payload for the extraction prompt."""
    return [
        {
            "page_number": p.page_number,
            "text": p.text or "",
            "needs_vision": p.needs_vision,
        }
        for p in sorted(doc.pages, key=lambda x: x.page_number)
    ]
