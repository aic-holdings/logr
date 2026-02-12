"""Tests for distributed tracing span endpoints."""
import uuid
from datetime import datetime, timezone, timedelta


def test_create_span(client, auth_headers):
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/v1/spans",
        headers=auth_headers,
        json={
            "trace_id": f"trace-{uuid.uuid4().hex[:8]}",
            "span_id": f"span-{uuid.uuid4().hex[:8]}",
            "service": "test-suite",
            "operation": "test_operation",
            "kind": "internal",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(seconds=1)).isoformat(),
            "duration_ms": 1000.0,
            "status": "ok",
            "attributes": {"test": True},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["service"] == "test-suite"
    assert data["operation"] == "test_operation"
    assert data["duration_ms"] == 1000.0


def test_create_span_with_parent(client, auth_headers):
    now = datetime.now(timezone.utc)
    tid = f"trace-{uuid.uuid4().hex[:8]}"
    parent_sid = f"span-parent-{uuid.uuid4().hex[:8]}"
    child_sid = f"span-child-{uuid.uuid4().hex[:8]}"

    # Create parent span
    client.post(
        "/v1/spans",
        headers=auth_headers,
        json={
            "trace_id": tid,
            "span_id": parent_sid,
            "service": "test-suite",
            "operation": "parent_op",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(seconds=2)).isoformat(),
            "duration_ms": 2000.0,
        },
    )

    # Create child span
    resp = client.post(
        "/v1/spans",
        headers=auth_headers,
        json={
            "trace_id": tid,
            "span_id": child_sid,
            "parent_span_id": parent_sid,
            "service": "test-suite",
            "operation": "child_op",
            "start_time": (now + timedelta(milliseconds=100)).isoformat(),
            "end_time": (now + timedelta(seconds=1)).isoformat(),
            "duration_ms": 900.0,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["parent_span_id"] == parent_sid


def test_batch_create_spans(client, auth_headers):
    now = datetime.now(timezone.utc)
    tid = f"trace-batch-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/v1/spans/batch",
        headers=auth_headers,
        json={
            "spans": [
                {
                    "trace_id": tid,
                    "span_id": f"span-batch-{i}-{uuid.uuid4().hex[:6]}",
                    "service": "test-suite",
                    "operation": f"batch_op_{i}",
                    "start_time": now.isoformat(),
                    "duration_ms": 100.0 * (i + 1),
                }
                for i in range(3)
            ]
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["accepted"] == 3
    assert data["failed"] == 0


def test_get_trace_spans(client, auth_headers):
    now = datetime.now(timezone.utc)
    tid = f"trace-get-{uuid.uuid4().hex[:8]}"
    root_sid = f"span-root-{uuid.uuid4().hex[:8]}"

    # Create root span
    client.post(
        "/v1/spans",
        headers=auth_headers,
        json={
            "trace_id": tid,
            "span_id": root_sid,
            "service": "test-suite",
            "operation": "root",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(seconds=3)).isoformat(),
            "duration_ms": 3000.0,
        },
    )

    resp = client.get(f"/v1/spans/trace/{tid}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == tid
    assert len(data["spans"]) >= 1
    assert "test-suite" in data["services"]


def test_get_nonexistent_trace_spans_returns_404(client, auth_headers):
    resp = client.get("/v1/spans/trace/no-such-trace", headers=auth_headers)
    assert resp.status_code == 404


def test_list_spans(client, auth_headers):
    resp = client.get("/v1/spans", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_spans_filter_by_service(client, auth_headers):
    resp = client.get(
        "/v1/spans",
        headers=auth_headers,
        params={"service": "test-suite"},
    )
    assert resp.status_code == 200
    for span in resp.json():
        assert span["service"] == "test-suite"
