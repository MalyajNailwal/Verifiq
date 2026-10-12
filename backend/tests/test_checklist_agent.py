"""ChecklistAgent tests — YAML-config required/expired document flags."""

import json

import pytest

from app.core.config import Settings
from app.models import Case, Document, ExtractedField
from app.models.enums import DocType, Severity
from app.services.checklist import load_checklists, run_checklist


@pytest.fixture()
def settings() -> Settings:
    return Settings(DATABASE_URL="sqlite://", LLM_PROVIDER="mock")  # type: ignore[call-arg]


def _case(db_session, asset_type: str, doc_types: list[str], deed_date: str | None = None) -> Case:
    case = Case(asset_name="Plot 42", asset_type=asset_type)
    db_session.add(case)
    db_session.flush()
    for dt in doc_types:
        doc = Document(
            case=case, doc_type=dt, original_filename=f"{dt}.txt", file_path=f"x/{dt}.txt"
        )
        db_session.add(doc)
        db_session.flush()
        if deed_date and dt == DocType.TITLE_DEED:
            db_session.add(
                ExtractedField(
                    document_id=doc.id,
                    field_name="document_issue_date",
                    value=json.dumps(deed_date),
                    confidence=0.95,
                    source_page=1,
                    extraction_reason="ok",
                )
            )
    db_session.commit()
    return case


def _rules(case: Case) -> set[str]:
    return {f.rule_id for f in case.flags}


def test_real_estate_complete_pack_no_flags(db_session, settings) -> None:
    case = _case(
        db_session,
        "real_estate",
        [
            DocType.TITLE_DEED,
            DocType.VALUATION_REPORT,
            DocType.LEGAL_OPINION,
        ],
        deed_date="2026-05-01",
    )
    run_checklist(db_session, case, settings)
    missing = [f for f in case.flags if f.rule_id.startswith("missing_doc")]
    assert missing == []


def test_missing_required_docs_flagged_high(db_session, settings) -> None:
    case = _case(db_session, "real_estate", [DocType.TITLE_DEED])
    run_checklist(db_session, case, settings)
    rules = _rules(case)
    assert "missing_doc:valuation_report" in rules
    assert "missing_doc:legal_opinion" in rules
    assert "missing_doc:title_deed" not in rules
    flag = next(f for f in case.flags if f.rule_id == "missing_doc:valuation_report")
    assert flag.severity == Severity.HIGH
    assert flag.flag_type == "missing_doc"


def test_expired_title_deed_flagged(db_session, settings) -> None:
    # title_deed has no valid_months in config; use legal_opinion expiry instead:
    case = _case(
        db_session,
        "real_estate",
        [
            DocType.TITLE_DEED,
            DocType.VALUATION_REPORT,
            DocType.LEGAL_OPINION,
        ],
    )
    # attach old issue date to legal opinion via direct field
    legal = next(d for d in case.documents if d.doc_type == DocType.LEGAL_OPINION)
    db_session.add(
        ExtractedField(
            document_id=legal.id,
            field_name="document_issue_date",
            value=json.dumps("2020-01-01"),
            confidence=0.9,
            source_page=1,
            extraction_reason="ok",
        )
    )
    db_session.commit()
    run_checklist(db_session, case, settings)
    assert "expired_doc:legal_opinion" in _rules(case)


def test_optional_doc_absence_silent(db_session, settings) -> None:
    case = _case(
        db_session,
        "real_estate",
        [
            DocType.TITLE_DEED,
            DocType.VALUATION_REPORT,
            DocType.LEGAL_OPINION,
        ],
    )
    run_checklist(db_session, case, settings)
    assert "missing_doc:spv_papers" not in _rules(case)


def test_unknown_asset_type_uses_default(db_session, settings) -> None:
    case = _case(db_session, "spacecraft", [DocType.VALUATION_REPORT])
    run_checklist(db_session, case, settings)
    assert "missing_doc:title_deed" in _rules(case)


def test_checklist_yaml_loads() -> None:
    data = load_checklists()
    assert "default" in data
    assert "real_estate" in data
