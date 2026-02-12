"""Tests for health, metrics, and root endpoints (no auth required)."""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "logr"
    assert data["database"]["status"] == "connected"


def test_health_includes_features(client):
    data = client.get("/health").json()
    assert "features" in data
    assert "retention_days" in data["features"]
    assert isinstance(data["features"]["retention_days"], int)


def test_root_returns_api_info(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "logr"
    assert "endpoints" in data
    assert "/v1/logs" in data["endpoints"].values()


def test_metrics_returns_200(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "uptime_seconds" in data
    assert "total_requests" in data
    assert data["uptime_seconds"] > 0


def test_prometheus_metrics(client):
    resp = client.get("/metrics/prometheus")
    assert resp.status_code == 200
    assert "logr_uptime_seconds" in resp.text
    assert "logr_requests_total" in resp.text


def test_openapi_docs(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["info"]["title"] == "Logr"
