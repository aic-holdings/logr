"""Tests for embedding pipeline admin endpoint."""


def test_embedding_status(client, master_headers):
    """Admin can check embedding pipeline status."""
    resp = client.get("/v1/admin/embeddings/status", headers=master_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "running" in data
    assert "daily_count" in data
    assert "daily_cap" in data
    assert "total_embedded" in data
    assert "total_errors" in data
    assert "config" in data
    assert data["config"]["embedding_model"] == "text-embedding-3-small"
    assert "logr" in data["config"]["excluded_services"]
    assert "artemis" in data["config"]["excluded_services"]


def test_embedding_status_requires_master_key(client, auth_headers):
    """Regular API key cannot access embedding status."""
    resp = client.get("/v1/admin/embeddings/status", headers=auth_headers)
    assert resp.status_code == 401
