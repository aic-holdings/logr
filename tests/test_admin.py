"""Tests for admin endpoints (require master key)."""
import uuid


def test_admin_stats(client, master_headers):
    resp = client.get("/v1/admin/stats", headers=master_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "events" in data
    assert "spans" in data
    assert "service_accounts" in data
    assert "api_keys" in data
    assert "date_range" in data
    assert "retention_days" in data


def test_list_service_accounts(client, master_headers):
    resp = client.get("/v1/admin/service-accounts", headers=master_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "service_accounts" in data
    assert isinstance(data["service_accounts"], list)


def test_create_service_account(client, master_headers):
    name = f"test-admin-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/v1/admin/service-accounts",
        headers=master_headers,
        json={"name": name, "description": "Admin test account"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == name
    assert data["api_key"].startswith("logr_")
    assert "key_prefix" in data


def test_create_duplicate_service_account_returns_400(client, master_headers):
    name = f"test-dup-{uuid.uuid4().hex[:8]}"
    # First create
    client.post(
        "/v1/admin/service-accounts",
        headers=master_headers,
        json={"name": name},
    )
    # Duplicate
    resp = client.post(
        "/v1/admin/service-accounts",
        headers=master_headers,
        json={"name": name},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


def test_list_api_keys(client, master_headers):
    resp = client.get("/v1/admin/keys", headers=master_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "keys" in data
    assert isinstance(data["keys"], list)


def test_issue_and_revoke_key(client, master_headers):
    # Create a service account first
    name = f"test-key-{uuid.uuid4().hex[:8]}"
    client.post(
        "/v1/admin/service-accounts",
        headers=master_headers,
        json={"name": name},
    )

    # Issue an additional key
    issue_resp = client.post(
        "/v1/admin/keys",
        headers=master_headers,
        json={
            "service_account_name": name,
            "key_name": "extra-key",
            "can_write": True,
            "can_read": True,
        },
    )
    assert issue_resp.status_code == 200
    key_data = issue_resp.json()
    assert key_data["api_key"].startswith("logr_")

    # Revoke it
    revoke_resp = client.delete(
        f"/v1/admin/keys/{key_data['id']}", headers=master_headers
    )
    assert revoke_resp.status_code == 200
    assert "revoked" in revoke_resp.json()["message"]


def test_retention_stats(client, master_headers):
    resp = client.get("/v1/admin/retention/stats", headers=master_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_logs" in data
    assert "retention_days" in data
    assert data["retention_days"] == 90


def test_retention_cleanup_dry_run(client, master_headers):
    resp = client.post(
        "/v1/admin/retention/cleanup",
        headers=master_headers,
        params={"dry_run": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert "logs_to_delete" in data
