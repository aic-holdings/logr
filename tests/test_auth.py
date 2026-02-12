"""Tests for authentication and authorization."""


def test_no_auth_header_returns_401(client):
    resp = client.get("/v1/logs")
    assert resp.status_code == 401
    assert "Authorization" in resp.json()["detail"]


def test_invalid_bearer_token_returns_401(client):
    resp = client.get(
        "/v1/logs",
        headers={"Authorization": "Bearer logr_invalid_key_12345"},
    )
    assert resp.status_code == 401


def test_malformed_auth_header_returns_401(client):
    resp = client.get(
        "/v1/logs",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp.status_code == 401


def test_valid_key_returns_200(client, auth_headers):
    resp = client.get("/v1/logs", headers=auth_headers)
    assert resp.status_code == 200


def test_master_key_on_admin_endpoint(client, master_headers):
    resp = client.get("/v1/admin/stats", headers=master_headers)
    assert resp.status_code == 200


def test_service_key_on_admin_endpoint_returns_401(client, auth_headers):
    resp = client.get("/v1/admin/stats", headers=auth_headers)
    assert resp.status_code == 401
