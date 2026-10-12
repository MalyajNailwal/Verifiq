"""LangGraph pipeline wiring (Phase 4).

Graph:  ingest → extract → crosscheck(+checklist) → report → route

LangGraph is optional at runtime: if it's not installed, the same nodes run
in sequence with plain Python (identical behavior, same state dict). This
keeps the MVP dependency-light while the graph gives us conditional edges +
checkpointing when available.

State is a plain dict so it serializes cleanly for LangGraph checkpointers.
"""

import logging
import uuid
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.llm.base import LLMClient
from app.models import Case, Document, ExtractedField
from app.models.enums import CaseStatus, OcrStatus
from app.services import crosscheck
from app.services import report as report_svc
from app.services.checklist import run_checklist
from app.services.extraction import ExtractionError, extract_document
from app.services.ingest import IngestError, ingest_document
from app.services.router_node import route_case
from app.services.storage import LocalStorage, StorageError

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    case_id: str
    doc_results: list[dict[str, Any]]
    errors: list[str]


def _node_ingest_and_extract(db: Session, llm: LLMClient, settings: Settings):
    def node(state: PipelineState) -> PipelineState:
        case = db.get(Case, uuid.UUID(state["case_id"]))
        results: list[dict[str, Any]] = []
        for doc in list(case.documents):
            results.append(_process_document(db, doc, llm, settings))
        return {"case_id": state["case_id"], "doc_results": results}

    return node


def _node_crosscheck(db: Session, settings: Settings):
    def node(state: PipelineState) -> PipelineState:
        case = db.get(Case, uuid.UUID(state["case_id"]))
        crosscheck.run_crosscheck(db, case, settings)
        run_checklist(db, case, settings)
        db.refresh(case)
        return {**state, "errors": state.get("errors", [])}

    return node


def _node_report(db: Session, llm: LLMClient, settings: Settings):
    def node(state: PipelineState) -> PipelineState:
        case = db.get(Case, uuid.UUID(state["case_id"]))
        report_svc.generate_report(db, case, llm, settings)
        return state

    return node


def _node_route(db: Session, settings: Settings):
    def node(state: PipelineState) -> PipelineState:
        case = db.get(Case, uuid.UUID(state["case_id"]))
        final = route_case(db, case, settings)
        return {**state, "final_status": final}

    return node


def _process_document(
    db: Session, doc: Document, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    doc_ids = {doc.id}
    has_fields = (
        db.query(ExtractedField).filter(ExtractedField.document_id.in_(doc_ids)).first() is not None
    )
    if doc.ocr_status == OcrStatus.DONE and has_fields:
        return {"document_id": str(doc.id), "ingested": False, "extracted": False}

    try:
        if doc.ocr_status != OcrStatus.DONE:
            storage = LocalStorage(settings.storage_dir)
            if not storage.exists(doc.file_path):
                raise StorageError(f"stored file missing: {doc.file_path}")
            ingest_document(db, doc, absolute_path=str(storage.root / doc.file_path))
    except (IngestError, StorageError, OSError) as exc:
        logger.error("ingest_failed document_id=%s err=%s", doc.id, exc)
        return {
            "document_id": str(doc.id),
            "ingested": False,
            "extracted": False,
            "error": str(exc),
        }

    try:
        extract_document(db, doc, llm, settings)
        return {"document_id": str(doc.id), "ingested": True, "extracted": True}
    except ExtractionError as exc:
        logger.error("extraction_failed document_id=%s err=%s", doc.id, exc)
        return {"document_id": str(doc.id), "ingested": True, "extracted": False, "error": str(exc)}


def run_pipeline(
    db: Session, case_id: uuid.UUID, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    """Run the full graph for a case; returns final state summary."""
    case = db.get(Case, case_id)
    if case is None:
        raise ValueError(f"case {case_id} not found")
    case.status = CaseStatus.PROCESSING
    db.commit()

    state: PipelineState = {"case_id": str(case_id), "doc_results": [], "errors": []}

    try:
        from langgraph.graph import END, StateGraph  # optional

        graph = StateGraph(PipelineState)
        graph.add_node("ingest_extract", _node_ingest_and_extract(db, llm, settings))
        graph.add_node("crosscheck", _node_crosscheck(db, settings))
        graph.add_node("report", _node_report(db, llm, settings))
        graph.add_node("route", _node_route(db, settings))
        graph.set_entry_point("ingest_extract")
        graph.add_edge("ingest_extract", "crosscheck")
        graph.add_edge("crosscheck", "report")
        graph.add_edge("report", "route")
        graph.add_edge("route", END)
        app = graph.compile()
        final = app.invoke(state)
        logger.info("pipeline_done case_id=%s via=langgraph", case_id)
        return dict(final)
    except ImportError:
        # Deterministic sequential fallback — same nodes, same order.
        state = _node_ingest_and_extract(db, llm, settings)(state)
        state = _node_crosscheck(db, settings)(state)
        state = _node_report(db, llm, settings)(state)
        state = _node_route(db, settings)(state)
        logger.info("pipeline_done case_id=%s via=sequential", case_id)
        return dict(state)
