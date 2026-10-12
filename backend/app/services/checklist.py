"""ChecklistAgent — config-driven (YAML) required-documents verification.

Per asset_type:
- a required doc_type with no Document row ⇒ missing_doc flag (HIGH)
- a present doc with valid_months and document_issue_date (or document date
  from its fields) older than that ⇒ expired_doc flag (MEDIUM)
- unknown asset types fall back to the `default` checklist
"""

import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Case, Document, ExtractedField, Flag
from app.models.enums import FlagType, Severity
from app.services.rules import date_value, months_since

logger = logging.getLogger(__name__)

CHECKLIST_PATH = Path(__file__).resolve().parent / "checklists.yaml"


class ChecklistConfigError(Exception):
    pass


@lru_cache(maxsize=1)
def load_checklists(path: str = str(CHECKLIST_PATH)) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "default" not in data:
        raise ChecklistConfigError("checklists.yaml must map asset types and define 'default'")
    return data


def _checklist_for(asset_type: str) -> dict:
    all_lists = load_checklists()
    return all_lists.get(asset_type) or all_lists["default"]


def _doc_issue_date(db: Session, doc: Document) -> tuple[datetime | None, ExtractedField | None]:
    """Best date for validity checks + the field row (query-based: relationships
    loaded eagerly before this run may be stale)."""
    rows = (
        db.query(ExtractedField)
        .filter_by(document_id=doc.id, field_name="document_issue_date")
        .all()
    )
    for f in rows:
        if f.value:
            try:
                raw = json.loads(f.value)
            except (TypeError, ValueError):
                raw = f.value
            if isinstance(raw, str):
                return date_value(raw), f
    return None, None


def run_checklist(db: Session, case: Case, settings: Settings) -> list[Flag]:
    """Append missing-doc / expired-doc flags for the case. Returns new flags."""
    checklist = _checklist_for(case.asset_type)
    present_types = {d.doc_type for d in case.documents}
    flags: list[Flag] = []

    for entry in checklist.get("required", []) + checklist.get("optional", []):
        doc_type = entry["doc_type"]
        if doc_type not in present_types:
            if entry.get("required", False):
                flags.append(
                    Flag(
                        case=case,
                        severity=Severity.HIGH,
                        flag_type=FlagType.MISSING_DOC,
                        description=f"Required document missing: {doc_type}",
                        rule_id=f"missing_doc:{doc_type}",
                        related_fields=[],
                    )
                )
                continue
            # optional docs absent: silent
            continue

        valid_months = entry.get("valid_months")
        if valid_months:
            for doc in [d for d in case.documents if d.doc_type == doc_type]:
                issue, field = _doc_issue_date(db, doc)
                if issue is not None:
                    age = months_since(issue)
                    if age is not None and age > valid_months:
                        raw_value = field.value
                        try:
                            raw_value = json.loads(field.value)
                        except (TypeError, ValueError):
                            pass
                        flags.append(
                            Flag(
                                case=case,
                                severity=Severity.MEDIUM,
                                flag_type=FlagType.EXPIRED_DOC,
                                description=(
                                    f"{doc_type} appears expired: dated {raw_value} "
                                    f"({age:.0f} months, limit {valid_months})"
                                ),
                                rule_id=f"expired_doc:{doc_type}",
                                related_fields=[
                                    {
                                        "document_id": str(doc.id),
                                        "field_name": "document_issue_date",
                                        "value": raw_value,
                                    }
                                ]
                                if field
                                else [],
                            )
                        )

    if flags:
        keep = db.query(Flag).filter(Flag.case_id == case.id).all()
        case.flags = keep + flags
        db.commit()
    logger.info("checklist_done case_id=%s new_flags=%d", case.id, len(flags))
    return flags
