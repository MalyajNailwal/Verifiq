"""Case endpoints: create → upload documents → run pipeline → inspect."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.llm import get_llm_client
from app.models import Case, Document, ExtractedField, Flag
from app.models.enums import CaseStatus, DocType, OcrStatus
from app.schemas import CaseCreate, CaseDetail, CaseOut, DocumentOut, ExtractedFieldOut
from app.services.storage import LocalStorage, StorageError, sanitize_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["cases"])

VALID_DOC_TYPES = {d.value for d in DocType}


def _get_case_or_404(db: Session, case_id: str) -> Case:
    try:
        cid = uuid.UUID(case_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid case id") from exc
    case = db.get(Case, cid)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    return case


@router.post("", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> Case:
    case = Case(
        asset_name=payload.asset_name,
        asset_type=payload.asset_type or "real_estate",
        jurisdiction=payload.jurisdiction,
        status=CaseStatus.UPLOADED,
    )
    db.add(case)
    db.commit()
    logger.info("case_created id=%s asset=%r", case.id, case.asset_name)
    return case


@router.post("/{case_id}/documents", response_model=list[DocumentOut], status_code=201)
def upload_documents(
    case_id: str,
    files: list[UploadFile] = File(...),
    doc_types: list[str] = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[Document]:
    """Upload one or more files. `doc_types` must be parallel to `files`."""
    case = _get_case_or_404(db, case_id)
    if case.status not in (CaseStatus.UPLOADED, CaseStatus.PROCESSING):
        raise HTTPException(409, f"cannot add documents to case in status {case.status}")
    if len(files) != len(doc_types):
        raise HTTPException(400, "files and doc_types must have the same length")

    storage = LocalStorage(settings.storage_dir)
    docs: list[Document] = []
    for file, doc_type in zip(files, doc_types, strict=True):
        if doc_type not in VALID_DOC_TYPES:
            raise HTTPException(400, f"invalid doc_type '{doc_type}'")
        data = file.file.read()
        filename = sanitize_filename(file.filename or "upload.bin")
        try:
            stored = storage.save_bytes(case.id, doc_type, filename, data)
        except StorageError as exc:
            raise HTTPException(400, str(exc)) from exc
        docs.append(
            Document(
                case=case,
                doc_type=doc_type,
                original_filename=filename,
                file_path=stored["path"],
                mime_type=file.content_type,
                file_size_bytes=stored["size"],
                sha256=stored["sha256"],
                ocr_status=OcrStatus.PENDING,
            )
        )
    db.add_all(docs)
    db.commit()
    logger.info("documents_uploaded case_id=%s count=%d", case.id, len(docs))
    return docs


def _run_pipeline_bg(case_id: str) -> None:
    """BackgroundTasks entrypoint — owns its own DB session."""
    from app.core.db import SessionLocal
    from app.services.graph import run_pipeline

    settings = get_settings()
    db = SessionLocal()
    try:
        llm = get_llm_client(settings)
        run_pipeline(db, uuid.UUID(case_id), llm, settings)
    except Exception:  # noqa: BLE001 — background task must never crash the app
        logger.exception("pipeline_background_failed case_id=%s", case_id)
        # mark the case so it isn't stuck in PROCESSING forever
        try:
            case = db.get(Case, uuid.UUID(case_id))
            if case is not None and case.status == CaseStatus.PROCESSING:
                from app.models.enums import CaseStatus as CS

                case.status = CS.NEEDS_REVIEW
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


@router.post("/{case_id}/run", status_code=202)
def run_case(
    case_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Kick off the verification pipeline asynchronously."""
    case = _get_case_or_404(db, case_id)
    if case.status == CaseStatus.PROCESSING:
        raise HTTPException(409, "case already processing")
    if not case.documents:
        raise HTTPException(400, "upload documents before running the pipeline")
    case.status = CaseStatus.PROCESSING
    db.commit()
    background.add_task(_run_pipeline_bg, str(case.id))
    return {"case_id": str(case.id), "status": "processing", "detail": "pipeline started"}


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(get_db)) -> Case:
    from app.schemas.case import FlagSummary

    case = _get_case_or_404(db, case_id)
    flags = db.query(Flag).filter(Flag.case_id == case.id).all()
    detail = CaseDetail(
        documents=[DocumentOut.model_validate(d) for d in case.documents],
        fields=[
            ExtractedFieldOut.model_validate(f)
            for f in (
                db.query(ExtractedField)
                .join(Document, ExtractedField.document_id == Document.id)
                .filter(Document.case_id == case.id)
                .all()
            )
        ],
        flags=[
            FlagSummary(
                id=f.id,
                severity=str(f.severity),
                flag_type=str(f.flag_type),
                description=f.description,
                rule_id=f.rule_id,
                resolved=f.resolved,
                related_fields=f.related_fields,
            )
            for f in flags
        ],
        id=case.id,
        asset_name=case.asset_name,
        asset_type=case.asset_type,
        jurisdiction=case.jurisdiction,
        status=case.status,
        created_at=case.created_at,
    )
    return detail
