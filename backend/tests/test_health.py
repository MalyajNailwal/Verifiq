"""Health endpoint tests."""


def test_health_ok(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["llm_provider"] == "mock"
    assert body["confidence_threshold"] == 0.75


def test_health_reports_settings(test_settings, client) -> None:
    body = client.get("/health").json()
    assert body["app"] == test_settings.app_name
    assert "NOT investment advice" in test_settings.disclaimer
