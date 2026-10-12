"""API endpoint tests: create → upload → run (in-process) → detail/report/review."""

import json
import uuid

CANNED = json.dumps(
    {
        "fields": [
            {
                "field_name": "owner_name",
                "value": "Ananya Deshpande",
                "confidence": 0.97,
                "source_page": 1,
                "source_snippet": "Owner: Mrs. Ananya Deshpande",
                "reason": "ok",
            }
        ],
        "is_readable": True,
    }
)


def _session_for(client):
    """The conftest override is `lambda: db_session` — calling it returns THE
    session the API endpoints use, so inline runners share its state."""
    return list(client.app.dependency_overrides.values())[0]()


def _inline_runner(client):
    """Returns a stand-in for cases._run_pipeline_bg using the API's session
    AND the overridden test settings (storage dir must match the uploads)."""
    from app.core.config import get_settings
    from app.core.llm import MockLLMClient
    from app.services.graph import run_pipeline

    db_session = _session_for(client)
    settings = client.app.dependency_overrides[get_settings]()

    def runner(case_id: str) -> None:
        llm = MockLLMClient()
        llm.canned["DOCUMENT TEXT"] = CANNED
        llm.canned["RATING"] = json.dumps({"summary": "Verification summary."})
        run_pipeline(db_session, uuid.UUID(case_id), llm, settings)

    return runner


def test_create_and_get_case(client) -> None:
    resp = client.post(
        "/cases",
        json={
            "asset_name": "Plot 42, Riverside",
            "asset_type": "real_estate",
            "jurisdiction": "IN-KA",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "uploaded"
    case_id = body["id"]

    detail = client.get(f"/cases/{case_id}")
    assert detail.status_code == 200
    assert detail.json()["asset_name"] == "Plot 42, Riverside"
    assert detail.json()["flags"] == []


def test_case_404_and_400(client) -> None:
    assert client.get(f"/cases/{'0' * 8}-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/cases/not-a-uuid").status_code == 400


def test_upload_documents_and_types(client) -> None:
    case_id = client.post("/cases", json={"asset_name": "X", "asset_type": "real_estate"}).json()[
        "id"
    ]

    resp = client.post(
        f"/cases/{case_id}/documents",
        files=[
            ("files", ("deed.txt", b"deed text here", "text/plain")),
            ("files", ("valuation.txt", b"valuation text", "text/plain")),
        ],
        data={"doc_types": ["title_deed", "valuation_report"]},
    )
    assert resp.status_code == 201
    docs = resp.json()
    assert len(docs) == 2
    assert {d["doc_type"] for d in docs} == {"title_deed", "valuation_report"}

    bad = client.post(
        f"/cases/{case_id}/documents",
        files=[("files", ("x.txt", b"x", "text/plain"))],
        data={"doc_types": ["gene_sequence"]},
    )
    assert bad.status_code == 400

    mismatch = client.post(
        f"/cases/{case_id}/documents",
        files=[("files", ("x.txt", b"x", "text/plain"))],
        data={"doc_types": ["title_deed", "other"]},
    )
    assert mismatch.status_code == 400


def test_run_requires_documents(client) -> None:
    case_id = client.post("/cases", json={"asset_name": "X", "asset_type": "real_estate"}).json()[
        "id"
    ]
    assert client.post(f"/cases/{case_id}/run").status_code == 400


def test_full_flow_report_and_download(client, monkeypatch) -> None:
    from app.api import cases as cases_api

    monkeypatch.setattr(cases_api, "_run_pipeline_bg", _inline_runner(client))

    case_id = client.post(
        "/cases",
        json={
            "asset_name": "Plot 42",
            "asset_type": "real_estate",
        },
    ).json()["id"]
    up = client.post(
        f"/cases/{case_id}/documents",
        files=[
            ("files", ("deed.txt", b"Owner: Mrs. Ananya Deshpande and data here", "text/plain"))
        ],
        data={"doc_types": ["title_deed"]},
    )
    assert up.status_code == 201

    run_resp = client.post(f"/cases/{case_id}/run")
    assert run_resp.status_code == 202

    detail = client.get(f"/cases/{case_id}").json()
    assert detail["status"] in ("needs_review", "completed")
    assert len(detail["fields"]) == 14
    flag_rules = {f["rule_id"] for f in detail["flags"]}
    assert "missing_doc:valuation_report" in flag_rules

    report = client.get(f"/cases/{case_id}/report")
    assert report.status_code == 200
    assert report.json()["risk_rating"] in ("low", "medium", "high")
    assert report.json()["report_hash"]

    download = client.get(f"/cases/{case_id}/report/download")
    assert download.status_code == 200
    assert "DISCLAIMER" in download.text
    assert "Plot 42" in download.text


def test_review_queue_flow(client, monkeypatch) -> None:
    from app.api import cases as cases_api

    monkeypatch.setattr(cases_api, "_run_pipeline_bg", _inline_runner(client))

    case_id = client.post("/cases", json={"asset_name": "P", "asset_type": "real_estate"}).json()[
        "id"
    ]
    client.post(
        f"/cases/{case_id}/documents",
        files=[("files", ("deed.txt", b"deed with enough content here", "text/plain"))],
        data={"doc_types": ["title_deed"]},
    )
    client.post(f"/cases/{case_id}/run")

    tasks = client.get("/review-tasks").json()
    assert isinstance(tasks, list)
    if tasks:  # needs_review path taken (missing required valuation doc)
        task = tasks[0]
        resolved = client.post(
            f"/review-tasks/{task['id']}/resolve",
            json={
                "decision": "approved",
                "reviewer_notes": "checked manually",
                "decided_by": "reviewer1",
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "approved"

        detail = client.get(f"/cases/{case_id}").json()
        assert detail["status"] in ("completed", "needs_review")

        # double-resolve must 409
        again = client.post(
            f"/review-tasks/{task['id']}/resolve",
            json={
                "decision": "approved",
            },
        )
        assert again.status_code == 409
