"""Pipeline service — runs the Phase 2 part of the graph per case:
ingest every pending document, then run the ExtractionAgent on each.

CrossCheck / Checklist / Report / Router nodes arrive in Phases 3-4; this
service is structured so those nodes slot in behind the same entrypoint.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.llm.base import LLMClient
from app.models import Case, Document, ExtractedField
from app.models.enums import CaseStatus, OcrStatus
from app.services.extraction import ExtractionError, extract_document
from app.services.ingest import IngestError, ingest_document
from app.services.storage import LocalStorage, StorageError

logger = logging.getLogger(__name__)


@dataclass
class DocumentResult:
    document_id: uuid.UUID
    ingested: bool
    extracted: bool
    error: str | None = None


@dataclass
class PipelineResult:
    case_id: uuid.UUID
    status: str
    documents: list[DocumentResult]


def run_case_pipeline(
    db: Session, case_id: uuid.UUID, llm: LLMClient, settings: Settings
) -> PipelineResult:
    """Process all documents of a case. Phase 2 scope: ingest + extraction."""
    case = db.get(Case, case_id)
    if case is None:
        raise ValueError(f"case {case_id} not found")
    # Note: re-runs are allowed; document-level idempotency (skip processed
    # docs) makes them cheap. Concurrent-run locking arrives with Phase 4
    # when a real worker owns the transition.
    case.status = CaseStatus.PROCESSING
    db.commit()

    results: list[DocumentResult] = []
    for doc in list(case.documents):
        results.append(_process_document(db, doc, llm, settings))

    # Phase 4's RouterNode will finalize status (needs_review / completed).
    # For now the case stays PROCESSING unless nothing was extracted.
    if all(r.error is None for r in results) and results:
        case.status = CaseStatus.PROCESSING  # awaits Phase 3+ nodes
    db.commit()
    return PipelineResult(
        case_id=case.id,
        status=case.status,
        documents=results,
    )


def _process_document(
    db: Session, doc: Document, llm: LLMClient, settings: Settings
) -> DocumentResult:
    """Ingest + extract one document; errors are recorded, never raised past here."""
    # Idempotency: skip already-processed documents (query, not relationship,
    # so stale in-memory state can't trigger a duplicate LLM run).
    has_fields = db.query(ExtractedField).filter_by(document_id=doc.id).first() is not None
    if doc.ocr_status == OcrStatus.DONE and has_fields:
        return DocumentResult(doc.id, ingested=False, extracted=False, error=None)
    try:
        if doc.ocr_status != OcrStatus.DONE:
            storage = LocalStorage(settings.storage_dir)
            absolute = str(storage.root / doc.file_path)
            if not storage.exists(doc.file_path):
                raise StorageError(f"stored file missing: {doc.file_path}")
            ingest_document(db, doc, file_bytes=None, absolute_path=absolute)
    except (IngestError, StorageError, OSError) as exc:
        logger.error("ingest_failed document_id=%s err=%s", doc.id, exc)
        return DocumentResult(doc.id, ingested=False, extracted=False, error=str(exc))

    try:
        extract_document(db, doc, llm, settings)
        return DocumentResult(doc.id, ingested=True, extracted=True)
    except ExtractionError as exc:
        logger.error("extraction_failed document_id=%s err=%s", doc.id, exc)
        return DocumentResult(doc.id, ingested=True, extracted=False, error=str(exc))


def run_case_pipeline_bg(case_id: uuid.UUID) -> None:
    """Entry point for FastAPI BackgroundTasks (Phase 4 wires the endpoint)."""
    from app.core.llm import get_llm_client

    settings = Settings()  # type: ignore[call-arg]
    llm = get_llm_client(settings)
    db = SessionLocal()
    try:
        run_case_pipeline(db, case_id, llm, settings)
    finally:
        db.close()
