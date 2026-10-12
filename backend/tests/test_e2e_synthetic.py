"""Phase 7 e2e test — real synthetic case files, full pipeline.

Each case in backend/samples/cases/ flows through ingest → extract (mock LLM)
→ crosscheck → checklist → report → router. Assertions check the
deterministic buckets, not the mock-LLM wording.
"""

import json
import pathlib
import uuid

import pytest

from app.core.config import Settings
from app.core.llm import MockLLMClient
from app.models import Case, Document, Report
from app.models.enums import CaseStatus, DocType
from app.services import crosscheck as crosscheck_svc
from app.services import ingest as ingest_mod
from app.services import report as report_svc
from app.services import rules as rules_mod
from app.services.pipeline import run_case_pipeline
from app.services.storage import LocalStorage

SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "cases"

CASE1 = [
    (DocType.TITLE_DEED, "case1_clean_title_deed.txt"),
    (DocType.VALUATION_REPORT, "case1_clean_valuation.txt"),
    (DocType.LEGAL_OPINION, "case1_clean_legal_opinion.txt"),
]
CASE2 = [
    (DocType.TITLE_DEED, "case2_mismatch_title_deed.txt"),
    (DocType.VALUATION_REPORT, "case2_mismatch_valuation.txt"),
    (DocType.LEGAL_OPINION, "case2_mismatch_legal_opinion.txt"),
]
CASE3 = [
    (DocType.TITLE_DEED, "case3_missing_expired_title_deed.txt"),
    (DocType.VALUATION_REPORT, "case3_sample_valuation_old.txt"),
    (DocType.LEGAL_OPINION, "case3_sample_legal_opinion_old.txt"),
]

SUMMARY = (
    '{"summary": "Automated verification summary; flagged items need human '
    'review. This is not investment advice."}'
)


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        DATABASE_URL="sqlite://",
        LLM_PROVIDER="mock",
        STORAGE_DIR=str(tmp_path / "storage"),
    )


FIELD_OK = {"confidence": 0.95, "source_page": 1, "source_snippet": "x", "reason": "ok"}


def _field(name: str, value) -> dict:
    return {"field_name": name, "value": value, **FIELD_OK}


def _canned_json(fields: list[dict]) -> str:
    """Canned extraction payload (what the LLM would return for every doc)."""
    return json.dumps({"fields": fields, "document_summary": None, "is_readable": True})


def _mock_llm(payload: str) -> MockLLMClient:
    """Mock LLM. `payload` must be JSON the extraction prompt will validate."""
    llm = MockLLMClient()
    llm.canned["DOCUMENT TEXT"] = payload
    llm.canned["RATING"] = SUMMARY
    return llm


def _mock_llm_doc_specific(per_doc: dict[str, str], default: str) -> MockLLMClient:
    """Mock LLM returning a payload per doc_type (keyed by the doc_type marker
    in the extraction prompt: 'DOCUMENT TYPE: <doc_type>').

    Marker matching is first-match-wins in MockLLMClient, so the specific
    doc_type markers must be registered BEFORE the generic fallback.
    """
    llm = MockLLMClient()
    for marker, payload in per_doc.items():
        llm.canned[f"DOCUMENT TYPE: {marker}"] = payload
    llm.canned["DOCUMENT TYPE: "] = default
    llm.canned["RATING"] = SUMMARY
    return llm


def _mk_case(db_session, settings: Settings, docs: list) -> Case:
    case = Case(asset_name=f"Synthetic {uuid.uuid4().hex[:8]}", asset_type="real_estate")
    db_session.add(case)
    db_session.commit()
    storage = LocalStorage(settings.storage_dir)
    for doc_type, filename in docs:
        raw = (SAMPLES / filename).read_bytes()
        stored = storage.save_bytes(case.id, doc_type.value, filename, raw)
        db_session.add(
            Document(
                case=case,
                doc_type=doc_type,
                original_filename=filename,
                file_path=stored["path"],
                sha256=stored["sha256"],
            )
        )
    db_session.commit()
    return case


def _rule_ids(case: Case) -> set[str]:
    return {f.rule_id for f in case.flags}


class TestPhase7SyntheticCases:
    """Deterministic outcomes from synthetic case files through the pipeline.

    The mock LLM effectively plays the ExtractionAgent; its canned payload is
    chosen per case to mirror what real extraction shows the fixtures contain
    (the same owner names / areas / dates are literally in the .txt text).
    """

    def test_case1_clean_clears(self, db_session, settings) -> None:
        """All docs present, same owner, fresh dates, area drift 0.05% → LOW."""
        payload = _canned_json(
            [
                _field("owner_name", "Ananya Deshpande"),
                _field("area", {"value": 4000, "unit": "sq ft"}),
                _field("document_issue_date", "2026-08-20"),
            ]
        )
        llm = _mock_llm(payload)
        case = _mk_case(db_session, settings, CASE1)
        result = run_case_pipeline(db_session, case.id, llm, settings)

        assert result.status == CaseStatus.COMPLETED
        assert case.status == CaseStatus.COMPLETED
        unresolved = [f for f in case.flags if not f.resolved]
        assert unresolved == [], f"expected clean, got {[f.rule_id for f in unresolved]}"
        report = db_session.query(Report).filter_by(case_id=case.id).one()
        assert report.risk_rating == "low"
        assert "not investment advice" in report.summary

    def test_case2_area_mismatch_flags(self, db_session, settings) -> None:
        """Deed 4,000 sq ft vs valuation 5,000 sq ft (25% drift) → HIGH flag."""
        # Per-doc-type canned payloads: the extraction prompt carries the
        # doc_type marker, so each document gets its own extraction result.
        llm = _mock_llm_doc_specific(
            {
                "title_deed": _canned_json([_field("area", {"value": 4000, "unit": "sq ft"})]),
                "valuation_report": _canned_json(
                    [_field("area", {"value": 5000, "unit": "sq ft"})]
                ),
            },
            default=_canned_json([]),
        )
        case = _mk_case(db_session, settings, CASE2)
        result = run_case_pipeline(db_session, case.id, llm, settings)

        assert "area_mismatch" in _rule_ids(case)
        area_flag = next(f for f in case.flags if f.rule_id == "area_mismatch")
        assert area_flag.severity == "high"
        assert case.status == CaseStatus.NEEDS_REVIEW
        report = db_session.query(Report).filter_by(case_id=case.id).one()
        assert report.risk_rating == "high"
        # all 3 docs present → no missing_doc flags
        assert not any(r.startswith("missing_doc:") for r in _rule_ids(case))
        assert all(d.error is None for d in result.documents)

    def test_case3_stale_flags(self, db_session, settings) -> None:
        """Valuation/legal docs older than valid_months → expired flags."""
        llm = _mock_llm_doc_specific(
            {
                "valuation_report": _canned_json([_field("valuation_date", "2019-05-30")]),
                "legal_opinion": _canned_json([_field("document_issue_date", "2019-02-11")]),
            },
            default=_canned_json([]),
        )
        case = _mk_case(db_session, settings, CASE3)
        run_case_pipeline(db_session, case.id, llm, settings)

        rule_ids = _rule_ids(case)
        # stale valuation hits the crosscheck rule (stale_valuation), the
        # expired legal opinion hits the checklist rule (expired_doc:...)
        assert "stale_valuation" in rule_ids, rule_ids
        assert "expired_doc:legal_opinion" in rule_ids, rule_ids
        assert case.status in (CaseStatus.NEEDS_REVIEW, CaseStatus.COMPLETED)
        report = db_session.query(Report).filter_by(case_id=case.id).one()
        assert report.score_details["method"] == "deterministic_rules_v1"


class TestPhase7RuleUnit:
    """Rules exercised exactly per the synthetic-fixture scenarios."""

    def test_case1_area_within_tolerance(self) -> None:
        assert (
            rules_mod.areas_match_within(
                {"value": 4000, "unit": "sq ft"}, {"value": 4002, "unit": "sq ft"}, 2.0
            )
            is True
        )

    def test_case2_area_beyond_tolerance(self) -> None:
        assert (
            rules_mod.areas_match_within(
                {"value": 4000, "unit": "sq ft"}, {"value": 5000, "unit": "sq ft"}, 2.0
            )
            is False
        )

    def test_case3_stale_cutoff(self) -> None:
        issue = rules_mod.date_value("2019-05-30")
        assert issue is not None
        age = rules_mod.months_since(issue)
        assert age > 12  # valuation_max_age_months
        # legal_opinion limit is 24 (checklists.yaml) — also stale
        issue2 = rules_mod.date_value("2019-02-11")
        assert rules_mod.months_since(issue2) > 24

    def test_owner_fuzzy_match(self) -> None:
        assert rules_mod.names_match("S. K. Verma", "Suresh K. Verma")
        assert rules_mod.names_match("Ananya Deshpande", "Mrs. Ananya Deshpande")
        assert not rules_mod.names_match("Siddharth Iyer", "Siddharth Menon")


class TestPhase7FixturesAndServices:
    def test_expected_fixtures_exist(self) -> None:
        assert SAMPLES.is_dir()
        for docs in (CASE1, CASE2, CASE3):
            for _, filename in docs:
                assert (SAMPLES / filename).is_file(), filename
        # fixture content spot-checks (what the rules depend on)
        deed1 = (SAMPLES / "case1_clean_title_deed.txt").read_text()
        assert "Ananya Deshpande" in deed1 and "4,000 square feet" in deed1
        val2 = (SAMPLES / "case2_mismatch_valuation.txt").read_text()
        assert "5,000 square feet" in val2

    def test_fixture_ingests_to_pages(self, db_session, settings) -> None:
        case = _mk_case(db_session, settings, CASE1)
        doc = case.documents[0]
        storage = LocalStorage(settings.storage_dir)
        ingest_mod.ingest_document(db_session, doc, absolute_path=str(storage.root / doc.file_path))
        assert doc.page_count == 1
        assert "TITLE DEED" in doc.pages[0].text

    def test_crosscheck_entrypoint(self, db_session, settings) -> None:
        case = _mk_case(db_session, settings, CASE2)
        flags = crosscheck_svc.run_crosscheck(db_session, case, settings)
        assert isinstance(flags, list)

    def test_score_weights_ordered(self) -> None:
        assert report_svc.WEIGHTS["high"] > report_svc.WEIGHTS["medium"]
        assert report_svc.WEIGHTS["medium"] > report_svc.WEIGHTS["low"]


def test_expected_json_loadable() -> None:
    fixture = pathlib.Path(__file__).resolve().parent / "fixtures" / "expected_cases.json"
    data = json.loads(fixture.read_text())
    assert len(data["cases"]) == 3
