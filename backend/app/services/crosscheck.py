"""CrossCheckAgent — deterministic rule engine that compares fields across
documents and emits Flag rows.

Rules (each rule emits at most one flag per case, deduped by rule_id):
- owner_name_mismatch      fuzzy name comparison (rules.py)
- area_mismatch            >tolerance% drift after unit normalization
- address_mismatch         significant-token signature overlap too low
- parcel_mismatch          exact (case-insensitive) parcel/survey conflict
- stale_valuation          valuation older than N months
- unresolved_encumbrances  liens present in any document

Also emits high-severity / low-confidence flags from extraction results (the
RouterNode's triggers), so the whole case state is derivable from flags.
"""

import json
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Case, Document, ExtractedField, Flag
from app.models.enums import FlagType, Severity
from app.services.rules import (
    address_sigla,
    areas_match_within,
    date_value,
    months_since,
    names_match,
)

logger = logging.getLogger(__name__)

RULE_OWNER = "owner_name_mismatch"
RULE_AREA = "area_mismatch"
RULE_ADDRESS = "address_mismatch"
RULE_PARCEL = "parcel_mismatch"
RULE_STALE = "stale_valuation"
RULE_LIEN = "unresolved_encumbrances"
RULE_LOW_CONF = "low_confidence_field"


def _parsed(field: ExtractedField) -> str | list | dict | None:
    """Deserialize the stored JSON value string into a Python object."""
    if field.value is None:
        return None
    try:
        return json.loads(field.value)
    except (TypeError, ValueError):
        return field.value


def _field_map(documents: list[Document]) -> dict[str, list[tuple[Document, ExtractedField]]]:
    """field_name -> [(document, field), ...] for non-not_found fields with values."""
    out: dict[str, list[tuple[Document, ExtractedField]]] = defaultdict(list)
    for doc in documents:
        for f in doc.fields:
            if f.value is not None and f.extraction_reason != "not_found":
                out[f.field_name].append((doc, f))
    return out


def _mk_flag(
    case: Case,
    *,
    severity: Severity,
    flag_type: FlagType,
    description: str,
    rule_id: str,
    related: list[dict],
    rule_confidence: float = 1.0,
) -> Flag:
    return Flag(
        case=case,
        severity=severity,
        flag_type=flag_type,
        description=description,
        rule_id=rule_id,
        related_fields=related,
        rule_confidence=rule_confidence,
    )


def _ref(doc: Document, field: ExtractedField) -> dict:
    return {
        "document_id": str(doc.id),
        "document_type": doc.doc_type,
        "field_name": field.field_name,
        "value": field.value,
        "source_page": field.source_page,
    }


def _doc_name(doc: Document) -> str:
    return f"{doc.doc_type}({doc.original_filename})"


def run_crosscheck(db: Session, case: Case, settings: Settings) -> list[Flag]:
    """Compare extracted fields across documents; replace case flags with findings."""
    # Re-runnable: delete unresolved rule flags by query (relationship-safe),
    # then reassign the relationship so in-memory state stays consistent.
    existing = db.query(Flag).filter(Flag.case_id == case.id, Flag.resolved.is_(False)).all()
    for old in existing:
        db.delete(old)
    db.flush()

    documents = list(case.documents)
    fmap = _field_map(documents)
    flags: list[Flag] = []

    # --- owner name mismatch (fuzzy) ---
    owner_entries = fmap.get("owner_name", [])
    for i in range(len(owner_entries)):
        for j in range(i + 1, len(owner_entries)):
            d1, f1 = owner_entries[i]
            d2, f2 = owner_entries[j]
            v1, v2 = _parsed(f1), _parsed(f2)
            if isinstance(v1, str) and isinstance(v2, str) and not names_match(v1, v2):
                flags.append(
                    _mk_flag(
                        case,
                        severity=Severity.HIGH,
                        flag_type=FlagType.MISMATCH,
                        description=(
                            f"Owner name mismatch: '{v1}' [{_doc_name(d1)} p{f1.source_page}] "
                            f"vs '{v2}' [{_doc_name(d2)} p{f2.source_page}]"
                        ),
                        rule_id=RULE_OWNER,
                        related=[_ref(d1, f1), _ref(d2, f2)],
                        rule_confidence=0.9,
                    )
                )

    # --- area mismatch (> tolerance% after normalization) ---
    area_entries = fmap.get("area", [])
    for i in range(len(area_entries)):
        for j in range(i + 1, len(area_entries)):
            (d1, f1), (d2, f2) = area_entries[i], area_entries[j]
            if (
                areas_match_within(_parsed(f1), _parsed(f2), settings.area_mismatch_tolerance_pct)
                is False
            ):
                flags.append(
                    _mk_flag(
                        case,
                        severity=Severity.HIGH,
                        flag_type=FlagType.MISMATCH,
                        description=(
                            f"Area discrepancy beyond {settings.area_mismatch_tolerance_pct}% "
                            f"between {_doc_name(d1)} and {_doc_name(d2)}"
                        ),
                        rule_id=RULE_AREA,
                        related=[_ref(d1, f1), _ref(d2, f2)],
                        rule_confidence=0.95,
                    )
                )

    # --- parcel/survey mismatch ---
    parcel_entries = fmap.get("parcel_or_survey_number", [])
    parcels = {str(f.value).strip().strip('"').lower() for _, f in parcel_entries}
    if len(parcels) > 1:
        flags.append(
            _mk_flag(
                case,
                severity=Severity.HIGH,
                flag_type=FlagType.MISMATCH,
                description="Parcel/survey number differs across documents: "
                + ", ".join(sorted(parcels)),
                rule_id=RULE_PARCEL,
                related=[_ref(dd, ff) for dd, ff in parcel_entries],
            )
        )

    # --- address mismatch (signature overlap) ---
    addr_entries = fmap.get("property_address", [])
    if len(addr_entries) >= 2:
        sig0 = address_sigla(str(_parsed(addr_entries[0][1]) or ""))
        for d2, f2 in addr_entries[1:]:
            sig2 = address_sigla(str(_parsed(f2) or ""))
            inter, union = sig0 & sig2, sig0 | sig2
            overlap = len(inter) / len(union) if union else 1.0
            if union and overlap < 0.5:
                d1, f1 = addr_entries[0]
                flags.append(
                    _mk_flag(
                        case,
                        severity=Severity.MEDIUM,
                        flag_type=FlagType.MISMATCH,
                        description=(
                            f"Property address may differ between {_doc_name(d1)} and "
                            f"{_doc_name(d2)} (token overlap {overlap:.0%})"
                        ),
                        rule_id=RULE_ADDRESS,
                        related=[_ref(d1, f1), _ref(d2, f2)],
                        rule_confidence=0.7,
                    )
                )

    # --- stale valuation (> N months) ---
    val_date_entries = fmap.get("valuation_date", [])
    for d, f in val_date_entries:
        raw_date = _parsed(f)
        age = months_since(date_value(raw_date if isinstance(raw_date, str) else None))
        if age is not None and age > settings.valuation_max_age_months:
            flags.append(
                _mk_flag(
                    case,
                    severity=Severity.MEDIUM,
                    flag_type=FlagType.EXPIRED_DOC,
                    description=(
                        f"Valuation dated {raw_date} is {age:.0f} months old "
                        f"(limit {settings.valuation_max_age_months})"
                    ),
                    rule_id=RULE_STALE,
                    related=[_ref(d, f)],
                )
            )

    # --- unresolved encumbrances ---
    lien_entries = fmap.get("encumbrances_or_liens", [])
    for d, f in lien_entries:
        liens = _parsed(f)
        if not isinstance(liens, list) or not liens:
            continue
        flags.append(
            _mk_flag(
                case,
                severity=Severity.HIGH,
                flag_type=FlagType.OTHER,
                description=(
                    f"Encumbrance(s) recorded in {_doc_name(d)}: "
                    + "; ".join(str(x) for x in liens)
                ),
                rule_id=RULE_LIEN,
                related=[_ref(d, f)],
            )
        )

    # --- low-confidence fields (RouterNode trigger source) ---
    for doc in documents:
        for f in doc.fields:
            if f.confidence < settings.confidence_threshold and f.extraction_reason != "not_found":
                flags.append(
                    _mk_flag(
                        case,
                        severity=Severity.MEDIUM,
                        flag_type=FlagType.LOW_CONFIDENCE,
                        description=(
                            f"Field '{f.field_name}' confidence {f.confidence:.2f} below "
                            f"threshold {settings.confidence_threshold} in {_doc_name(doc)}"
                        ),
                        rule_id=RULE_LOW_CONF,
                        related=[_ref(doc, f)],
                        rule_confidence=1.0,
                    )
                )

    if flags:
        resolved = [f for f in case.flags if f.resolved]  # keep reviewer-decided ones
        case.flags = resolved + flags
    db.commit()
    logger.info(
        "crosscheck_done case_id=%s flags=%d high=%d",
        case.id,
        len(flags),
        sum(1 for f in flags if f.severity == Severity.HIGH),
    )
    return flags
