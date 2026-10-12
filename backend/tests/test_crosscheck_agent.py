"""CrossCheckAgent tests — deterministic rules over synthetic field states."""

import json

import pytest

from app.core.config import Settings
from app.models import Case, Document, ExtractedField
from app.models.enums import DocType, Severity
from app.services.crosscheck import run_crosscheck


@pytest.fixture()
def settings() -> Settings:
    return Settings(DATABASE_URL="sqlite://", LLM_PROVIDER="mock")  # type: ignore[call-arg]


def _case_with_docs(db_session, docs_spec: dict[str, dict]) -> Case:
    """docs_spec: {doc_type: {field_name: (value, confidence, page)}}"""
    case = Case(asset_name="Plot 42", asset_type="real_estate")
    db_session.add(case)
    db_session.flush()
    for doc_type, fields in docs_spec.items():
        doc = Document(
            case=case,
            doc_type=doc_type,
            original_filename=f"{doc_type}.txt",
            file_path=f"x/{doc_type}.txt",
        )
        db_session.add(doc)
        db_session.flush()
        for name, (value, conf, page) in fields.items():
            db_session.add(
                ExtractedField(
                    document_id=doc.id,
                    field_name=name,
                    value=json.dumps(value) if value is not None else None,
                    confidence=conf,
                    source_page=page,
                    extraction_reason="ok" if value is not None else "not_found",
                )
            )
    db_session.commit()
    return case


def _rule_ids(case: Case) -> set[str]:
    return {f.rule_id for f in case.flags}


def test_owner_mismatch_flagged_high(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"owner_name": ("Ravi Kumar", 0.97, 1)},
            DocType.SPV_PAPERS: {"owner_name": ("Suresh Patel", 0.95, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "owner_name_mismatch" in _rule_ids(case)
    flag = next(f for f in case.flags if f.rule_id == "owner_name_mismatch")
    assert flag.severity == Severity.HIGH
    assert len(flag.related_fields) == 2


def test_owner_variants_not_flagged(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"owner_name": ("Mr. Ravi Kumar", 0.97, 1)},
            DocType.SPV_PAPERS: {"owner_name": ("M. Ravi Kumar", 0.93, 2)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "owner_name_mismatch" not in _rule_ids(case)


def test_area_mismatch_beyond_tolerance(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"area": ({"value": 4000, "unit": "sq ft"}, 0.95, 1)},
            DocType.VALUATION_REPORT: {"area": ({"value": 5000, "unit": "sq ft"}, 0.95, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "area_mismatch" in _rule_ids(case)


def test_area_unit_normalized_no_false_positive(db_session, settings) -> None:
    # 4000 sq ft ≈ 371.6 sq m; declare same area in different units.
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"area": ({"value": 4000, "unit": "sq ft"}, 0.95, 1)},
            DocType.VALUATION_REPORT: {"area": ({"value": 371.6, "unit": "sq m"}, 0.95, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "area_mismatch" not in _rule_ids(case)


def test_area_unknown_unit_skipped(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"area": ({"value": 10, "unit": "cubits"}, 0.9, 1)},
            DocType.VALUATION_REPORT: {"area": ({"value": 900, "unit": "sq m"}, 0.9, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "area_mismatch" not in _rule_ids(case)


def test_parcel_mismatch(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"parcel_or_survey_number": ("112/3B", 0.98, 1)},
            DocType.LEGAL_OPINION: {"parcel_or_survey_number": ("118/7A", 0.95, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "parcel_mismatch" in _rule_ids(case)


def test_stale_valuation(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.VALUATION_REPORT: {
                "valuation_date": ("2023-01-15", 0.94, 1),  # > 12 months old
            },
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "stale_valuation" in _rule_ids(case)
    flag = next(f for f in case.flags if f.rule_id == "stale_valuation")
    assert flag.flag_type == "expired_doc"


def test_fresh_valuation_ok(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.VALUATION_REPORT: {"valuation_date": ("2026-09-01", 0.94, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "stale_valuation" not in _rule_ids(case)


def test_unresolved_liens(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.VALUATION_REPORT: {
                "encumbrances_or_liens": (["Mortgage in favour of HDFC Bank"], 0.88, 1),
            },
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "unresolved_encumbrances" in _rule_ids(case)
    flag = next(f for f in case.flags if f.rule_id == "unresolved_encumbrances")
    assert flag.severity == Severity.HIGH
    assert isinstance(flag.related_fields, list) and flag.related_fields


def test_low_confidence_flagged(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"owner_name": ("A D", 0.4, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert "low_confidence_field" in _rule_ids(case)


def test_not_found_fields_never_compared(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"owner_name": (None, 1.0, None)},
            DocType.SPV_PAPERS: {"owner_name": (None, 1.0, None)},
        },
    )
    run_crosscheck(db_session, case, settings)
    assert not _rule_ids(case) & {"owner_name_mismatch", "parcel_mismatch"}


def test_rerun_replaces_unresolved_flags(db_session, settings) -> None:
    case = _case_with_docs(
        db_session,
        {
            DocType.TITLE_DEED: {"owner_name": ("Ravi Kumar", 0.97, 1)},
            DocType.SPV_PAPERS: {"owner_name": ("Suresh Patel", 0.95, 1)},
        },
    )
    run_crosscheck(db_session, case, settings)
    n1 = len(case.flags)
    run_crosscheck(db_session, case, settings)  # idempotent
    n2 = len(case.flags)
    assert n1 == n2 == 1
