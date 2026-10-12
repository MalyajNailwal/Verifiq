"""Report endpoints — serve the generated verification report."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import Case, Report
from app.schemas.report import ReportOut
from app.services.anchor import AnchorError, anchor_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cases", tags=["reports"])

DISCLAIMER = (
    "\n\n---\nDISCLAIMER: This report is an automated document-verification and "
    "risk-flagging output. It is NOT investment advice and must not be relied upon "
    "to buy, sell, or invest in any asset. A qualified human reviewer must validate "
    "all flagged items before any further use.\n"
)


@router.get("/{case_id}/report", response_model=ReportOut)
def get_report(case_id: str, db: Session = Depends(get_db)) -> Report:
    case = db.get(Case, _uuid(case_id)) if _is_uuid(case_id) else None
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    report = db.query(Report).filter_by(case_id=case.id).first()
    if report is None:
        raise HTTPException(404, "report not generated yet — run the pipeline first")
    return report


@router.post("/{case_id}/report/anchor", response_model=ReportOut)
def anchor_case_report(
    case_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Report:
    """Anchor the report hash on Polygon Amoy testnet (Phase 6, optional).

    Requires POLYGON_ANCHOR_ENABLED=true, POLYGON_PRIVATE_KEY (funded with
    testnet POL) and `pip install '.[chain]'`. Idempotent — an anchored
    report returns its existing tx without re-submitting.
    """
    case = db.get(Case, _uuid(case_id)) if _is_uuid(case_id) else None
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    report = db.query(Report).filter_by(case_id=case.id).first()
    if report is None:
        raise HTTPException(404, "report not generated yet — run the pipeline first")
    try:
        result = anchor_report(db, report, settings)
    except AnchorError as exc:
        raise HTTPException(503, f"anchoring unavailable: {exc}") from exc
    logger.info("anchored case_id=%s tx=%s status=%s", case_id, result.tx_hash, result.status)
    db.refresh(report)
    return report


@router.get("/{case_id}/report/download", response_class=PlainTextResponse)
def download_report(case_id: str, db: Session = Depends(get_db)) -> str:
    """MVP deliverable: plain-text/markdown rendering of the report (PDF in Phase 7)."""
    case = db.get(Case, _uuid(case_id)) if _is_uuid(case_id) else None
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    report = db.query(Report).filter_by(case_id=case.id).first()
    if report is None:
        raise HTTPException(404, "report not generated yet — run the pipeline first")

    lines = [
        f"# Verification Report — {case.asset_name}",
        f"Case ID: {case.id}",
        f"Asset type: {case.asset_type}   Jurisdiction: {case.jurisdiction or 'n/a'}",
        f"Risk rating: {report.risk_rating.upper()}",
        f"Report hash (SHA-256): {report.report_hash}",
        "",
        "## Summary",
        report.summary,
        "",
        "## Document checklist",
    ]
    for entry in report.checklist or []:
        lines.append(
            f"- [{'x' if entry.get('present') else ' '}] {entry['doc_type']}"
            f" (required={'yes' if entry.get('required') else 'no'},"
            f" status={entry.get('status')})"
        )
    lines += ["", "## Flags"]
    for f in case.flags:
        marker = {"high": "[HIGH]", "medium": "[MED ]", "low": "[low ]"}.get(
            str(f.severity), "[flag]"
        )
        lines.append(f"- {marker} {f.description}{' (resolved)' if f.resolved else ''}")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def _is_uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _uuid(value: str):
    from uuid import UUID

    return UUID(value)
