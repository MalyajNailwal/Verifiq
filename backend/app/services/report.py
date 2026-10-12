"""ReportAgent — rule-based risk scoring + LLM-written plain-English summary.

Hard constraints honored here:
- The risk RATING is computed by deterministic rules only. The LLM writes the
  explanation wording — it can never change the rating.
- Every report carries the mandatory no-investment-advice disclaimer.
- The report JSON is canonicalized and hashed (SHA-256) — that hash is what a
  later phase anchors on-chain.
"""

import hashlib
import json
import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.llm.base import LLMClient
from app.core.prompts import build_prompt
from app.models import Case, Flag
from app.models.enums import RiskRating, Severity
from app.schemas.llm import SummaryResult
from app.services.checklist import run_checklist

logger = logging.getLogger(__name__)

PROMPT_NAME = "report_summary"
PROMPT_VERSION = "v1"

# Severity weights for the rule-based score.
WEIGHTS = {Severity.HIGH: 3.0, Severity.MEDIUM: 1.5, Severity.LOW: 0.5}


def score_case(flags: list[Flag]) -> tuple[RiskRating, dict]:
    """Deterministic risk rating from flags. LLM never changes this."""
    unresolved = [f for f in flags if not f.resolved]
    by_sev: dict[str, int] = {s.value: 0 for s in Severity}
    for f in unresolved:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    score = sum(WEIGHTS[Severity(s)] * n for s, n in by_sev.items())

    if by_sev["high"] > 0 or score >= 4.0:
        rating = RiskRating.HIGH
    elif score >= 1.5:
        rating = RiskRating.MEDIUM
    else:
        rating = RiskRating.LOW

    details = {
        "score": round(score, 2),
        "high_flags": by_sev["high"],
        "medium_flags": by_sev["medium"],
        "low_flags": by_sev["low"],
        "weights": {k.value: v for k, v in WEIGHTS.items()},
        "method": "deterministic_rules_v1",
    }
    return rating, details


def build_report_json(
    case: Case,
    rating: RiskRating,
    summary: str,
    checklist: list[dict],
    score_details: dict,
    disclaimer: str,
) -> dict:
    """Canonical report payload (also what gets hashed + served as JSON)."""
    return {
        "disclaimer": disclaimer,
        "case_id": str(case.id),
        "asset_name": case.asset_name,
        "asset_type": case.asset_type,
        "jurisdiction": case.jurisdiction,
        "risk_rating": rating.value,
        "summary": summary,
        "score_details": score_details,
        "checklist": checklist,
        "flags": [
            {
                "severity": f.severity if isinstance(f.severity, str) else f.severity.value,
                "type": f.flag_type if isinstance(f.flag_type, str) else f.flag_type.value,
                "description": f.description,
                "rule_id": f.rule_id,
                "resolved": f.resolved,
            }
            for f in case.flags
        ],
    }


def hash_report(report: dict) -> str:
    """SHA-256 over the canonical (sorted-keys, no-whitespace) JSON serialization."""
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_report(db: Session, case: Case, llm: LLMClient, settings: Settings) -> "Report":  # noqa: F821
    """Full report generation: checklist refresh → score → LLM summary → persist."""
    from app.models import Report  # local import avoids circulars

    # Checklist flags must be current before scoring.
    existing_rules = {f.rule_id for f in db.query(Flag).filter(Flag.case_id == case.id)}

    if not any(r.startswith("missing_doc") or r.startswith("expired_doc") for r in existing_rules):
        run_checklist(db, case, settings)
        db.refresh(case)

    rating, score_details = score_case(case.flags)

    summary = _llm_summary(db, case, llm, settings, rating)
    checklist = _checklist_view(case)

    report_payload = build_report_json(
        case, rating, summary, checklist, score_details, settings.disclaimer
    )
    digest = hash_report(report_payload)

    # One report per case: replace any prior version.
    prior = db.query(Report).filter_by(case_id=case.id).all()
    for p in prior:
        db.delete(p)
    db.flush()

    report = Report(
        case_id=case.id,
        risk_rating=rating.value,
        summary=summary,
        checklist=checklist,
        score_details=score_details,
        report_hash=digest,
        prompt_version=PROMPT_VERSION,
    )
    db.add(report)
    db.commit()
    logger.info("report_generated case_id=%s rating=%s hash=%s", case.id, rating, digest[:12])
    return report


def _checklist_view(case: Case) -> list[dict]:
    """Machine-readable doc-presence checklist for the report."""
    entries: dict[str, dict] = {}
    required = {"title_deed", "valuation_report", "legal_opinion"}
    for doc_type in ["title_deed", "valuation_report", "legal_opinion", "spv_papers", "other"]:
        entries[doc_type] = {
            "doc_type": doc_type,
            "required": doc_type in required,
            "present": False,
            "status": "missing",
            "note": None,
        }
    for flag in case.flags:
        if flag.rule_id and flag.rule_id.startswith("missing_doc:"):
            dt = flag.rule_id.split(":", 1)[1]
            if dt in entries:
                entries[dt]["note"] = "flagged missing"
    for doc in case.documents:
        e = entries.setdefault(
            doc.doc_type,
            {
                "doc_type": doc.doc_type,
                "required": doc.doc_type in required,
                "present": False,
                "status": "present",
                "note": None,
            },
        )
        e["present"] = True
        e["status"] = "present"
        if any(f.rule_id == f"expired_doc:{doc.doc_type}" for f in case.flags):
            e["status"] = "expired"
    return list(entries.values())


def _llm_summary(
    db: Session, case: Case, llm: LLMClient, settings: Settings, rating: RiskRating
) -> str:
    """LLM writes the wording ONLY — the rating and flags are already fixed."""
    flag_lines = (
        "\n".join(f"- [{f.severity}] {f.description}" for f in case.flags if not f.resolved)
        or "- none"
    )
    prompt, version = build_prompt(
        PROMPT_NAME,
        {
            "asset_name": case.asset_name,
            "asset_type": case.asset_type,
            "rating": rating.value,
            "flags": flag_lines,
        },
    )
    try:
        result = llm.complete_structured(
            prompt, SummaryResult, prompt_name=PROMPT_NAME, prompt_version=version
        )
        return result.summary
    except Exception as exc:  # noqa: BLE001 — report must not fail on LLM hiccups
        logger.warning("llm_summary_failed err=%s — using fallback text", exc)
        high = sum(1 for f in case.flags if f.severity == Severity.HIGH and not f.resolved)
        return _fallback_summary(case, rating, high, len(case.flags))


def _fallback_summary(case: Case, rating: RiskRating, high: int, total: int) -> str:
    if total == 0:
        detail = "No unresolved verification flags were raised."
    elif high:
        detail = f"{high} high-severity and {total - high} other verification flags were raised."
    else:
        detail = f"{total} verification flag(s) were raised, none high-severity."
    return (
        f"Document verification for '{case.asset_name}' ({case.asset_type}) is complete. "
        f"The automated risk rating is {rating.value.upper()}. {detail} "
        f"This is a document-verification result only — see the disclaimer."
    )
