"""Tests for search and anomaly detection endpoints."""
import uuid


def test_semantic_search_fallback(client, auth_headers):
    """Semantic search falls back to text search when embeddings aren't indexed."""
    # Create a log with a unique keyword
    keyword = f"searchable-{uuid.uuid4().hex[:8]}"
    client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": f"This log has keyword {keyword}",
        },
    )

    resp = client.post(
        "/v1/search/semantic",
        headers=auth_headers,
        json={"query": keyword, "limit": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == keyword
    assert isinstance(data["results"], list)


def test_semantic_search_with_filters(client, auth_headers):
    resp = client.post(
        "/v1/search/semantic",
        headers=auth_headers,
        json={
            "query": "error",
            "service": "test-suite",
            "level": "error",
            "limit": 5,
        },
    )
    assert resp.status_code == 200
    for result in resp.json()["results"]:
        assert result["service"] == "test-suite"
        assert result["level"] == "error"


def test_grouped_errors(client, auth_headers):
    resp = client.get(
        "/v1/search/errors/grouped",
        headers=auth_headers,
        params={"hours": 168},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    assert "time_window_hours" in data
    assert isinstance(data["groups"], list)


def test_anomaly_detection(client, auth_headers):
    resp = client.get(
        "/v1/search/anomalies",
        headers=auth_headers,
        params={"hours": 24},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "anomalies" in data
    assert "current_period" in data
    assert "previous_period" in data
    assert isinstance(data["anomalies"], list)


def test_anomaly_detection_filtered(client, auth_headers):
    resp = client.get(
        "/v1/search/anomalies",
        headers=auth_headers,
        params={"service": "test-suite", "hours": 48},
    )
    assert resp.status_code == 200
    assert "current_period" in resp.json()
