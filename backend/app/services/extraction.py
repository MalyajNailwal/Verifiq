"""ExtractionAgent — LLM extraction of key fields per document.

Contract:
- Prompt comes from versioned template app/prompts/extraction_v1.txt.
- Output is validated against ExtractionResult (Pydantic) inside
  LLMClient.complete_structured — invalid JSON retried automatically.
- Persisted ExtractedField rows always carry confidence + source reference.
- value=null with reason="not_found" is stored explicitly (constraint #5).
- Scanned pages (needs_vision) get a note appended to the prompt for the
  vision-capable model path (MVP: same text; Phase 3 renders page images).
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.llm.base import LLMClient
from app.core.prompts import PromptNotFoundError, build_prompt
from app.models import Document, ExtractedField, LLMCallLog
from app.schemas.llm import ExtractionResult
from app.services.ingest import pages_payload

logger = logging.getLogger(__name__)

PROMPT_NAME = "extraction"
PROMPT_VERSION = "v1"

KNOWN_FIELDS = {
    "owner_name",
    "property_address",
    "parcel_or_survey_number",
    "area",
    "valuation_amount",
    "valuation_date",
    "valuer_name",
    "encumbrances_or_liens",
    "legal_status",
    "registration_date",
    "spv_name",
    "signatory_names",
    "document_issue_date",
    "document_expiry_date",
}


class ExtractionError(Exception):
    pass


def _format_pages(pages: list[dict[str, Any]]) -> str:
    chunks = []
    for p in pages:
        marker = f"--- PAGE {p['page_number']} ---"
        if p["needs_vision"]:
            marker += " [SCANNED/LOW-TEXT PAGE]"
        chunks.append(f"{marker}\n{p['text']}")
    return "\n\n".join(chunks)


def extract_document(
    db: Session,
    doc: Document,
    llm: LLMClient,
    settings: Settings,
    *,
    prompt_version: str = PROMPT_VERSION,
) -> list[ExtractedField]:
    """Run LLM extraction for one document and persist ExtractedField rows.

    Returns the created field rows. Raises ExtractionError on prompt/LLM
    failure; the document's fields are replaced atomically on success.
    """
    pages = pages_payload(doc)
    if not pages:
        raise ExtractionError(f"document {doc.id} has no ingested pages")

    try:
        prompt, version = build_prompt(
            PROMPT_NAME,
            {"doc_type": doc.doc_type, "page_texts": _format_pages(pages)},
            version=prompt_version,
        )
    except PromptNotFoundError as exc:
        raise ExtractionError(str(exc)) from exc

    try:
        result: ExtractionResult = llm.complete_structured(
            prompt,
            ExtractionResult,
            prompt_name=PROMPT_NAME,
            prompt_version=version,
        )
    except Exception as exc:
        _log_call(
            db,
            llm,
            version,
            status="error",
            error=str(exc),
            case_id=doc.case_id,
            document_id=doc.id,
        )
        raise ExtractionError(f"LLM extraction failed: {exc}") from exc

    fields = _persist_fields(db, doc, result)
    _log_call(db, llm, version, status="ok", case_id=doc.case_id, document_id=doc.id)
    logger.info(
        "extraction_done document_id=%s fields=%d low_confidence=%d",
        doc.id,
        len(fields),
        sum(1 for f in fields if f.confidence < settings.confidence_threshold),
    )
    return fields


def _persist_fields(db: Session, doc: Document, result: ExtractionResult) -> list[ExtractedField]:
    """Replace the document's fields with validated LLM output."""
    doc.fields.clear()
    db.flush()

    created: list[ExtractedField] = []
    seen: set[str] = set()
    for cand in result.fields:
        if cand.field_name not in KNOWN_FIELDS:
            logger.warning("unknown field ignored field=%s", cand.field_name)
            continue
        if cand.field_name in seen:
            logger.warning("duplicate field kept first field=%s", cand.field_name)
            continue
        seen.add(cand.field_name)
        created.append(
            ExtractedField(
                document_id=doc.id,
                field_name=cand.field_name,
                value=(
                    json.dumps(cand.value, ensure_ascii=False) if cand.value is not None else None
                ),
                confidence=cand.confidence,
                source_page=cand.source_page,
                source_snippet=cand.source_snippet,
                extraction_reason=cand.reason or ("not_found" if cand.value is None else "ok"),
            )
        )
    # Guarantee every known field exists (null + not_found when absent).
    for missing in sorted(KNOWN_FIELDS - seen):
        created.append(
            ExtractedField(
                document_id=doc.id,
                field_name=missing,
                value=None,
                confidence=1.0,
                source_page=None,
                source_snippet=None,
                extraction_reason="not_found",
            )
        )
    db.add_all(created)
    doc.fields = created  # refresh in-memory relationship (selectin can be stale)
    db.commit()
    return created


def _log_call(
    db: Session,
    llm: LLMClient,
    prompt_version: str,
    *,
    status: str,
    error: str | None = None,
    case_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    last = llm.last_response
    db.add(
        LLMCallLog(
            provider=llm.provider,
            model=llm.model,
            prompt_name=PROMPT_NAME,
            prompt_version=prompt_version,
            call_type="complete_structured",
            status=status,
            error=error,
            latency_ms=last.latency_ms if last else None,
            prompt_tokens=last.prompt_tokens if last else None,
            completion_tokens=last.completion_tokens if last else None,
            total_tokens=last.total_tokens if last else None,
            case_id=str(case_id),
            document_id=str(document_id),
        )
    )
    db.commit()
