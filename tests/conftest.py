"""Test fixtures for logr integration tests against the live API."""
import os
import uuid

import httpx
import pytest

API_URL = os.environ.get(
    "LOGR_API_URL", "https://logr-api-production.up.railway.app"
)
MASTER_KEY = os.environ.get(
    "LOGR_MASTER_KEY",
    "logr_master_44e83d85297789c46aa3f5d7d78c3b782fb830833180d3ed",
)


@pytest.fixture(scope="session")
def api_url():
    return API_URL


@pytest.fixture(scope="session")
def master_key():
    return MASTER_KEY


@pytest.fixture(scope="session")
def master_headers():
    return {
        "Authorization": f"Bearer {MASTER_KEY}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="session")
def client():
    """Shared httpx client for all tests."""
    with httpx.Client(base_url=API_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def service_api_key(client, master_headers):
    """Create a test service account and return its API key."""
    name = f"test-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/v1/admin/service-accounts",
        headers=master_headers,
        json={"name": name, "description": "Integration test account"},
    )
    assert resp.status_code == 200, f"Failed to create service account: {resp.text}"
    return resp.json()["api_key"]


@pytest.fixture(scope="session")
def auth_headers(service_api_key):
    return {
        "Authorization": f"Bearer {service_api_key}",
        "Content-Type": "application/json",
    }


@pytest.fixture()
def trace_id():
    return f"test-trace-{uuid.uuid4().hex[:16]}"
