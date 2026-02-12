"""Tests for log ingestion and query endpoints."""
import uuid


def test_create_simple_log(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": "Simple test log entry",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["service"] == "test-suite"
    assert data["level"] == "info"
    assert data["message"] == "Simple test log entry"
    assert "id" in data
    assert "timestamp" in data


def test_create_log_with_all_fields(client, auth_headers, trace_id):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": "Full log entry with all fields",
            "context": {"test": True, "run_id": 42},
            "environment": "test",
            "host": "test-runner",
            "version": "0.1.0",
            "trace_id": trace_id,
            "span_id": "span-001",
            "request_id": "req-001",
            "user_id": "user-test",
            "session_id": "session-test",
            "duration_ms": 123.45,
            "model": "claude-3-opus",
            "tokens_in": 500,
            "tokens_out": 1200,
            "cost_usd": 0.045,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["trace_id"] == trace_id
    assert data["model"] == "claude-3-opus"
    assert data["tokens_in"] == 500
    assert data["tokens_out"] == 1200
    assert data["duration_ms"] == 123.45
    assert data["context"]["test"] is True


def test_create_log_with_events(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": "LLM completion with events",
            "model": "claude-3-opus",
            "tokens_in": 100,
            "tokens_out": 200,
            "events": [
                {
                    "event_type": "system_prompt",
                    "content": "You are a test assistant.",
                    "sequence": 0,
                },
                {
                    "event_type": "prompt",
                    "content": "Hello world",
                    "sequence": 1,
                },
                {
                    "event_type": "completion",
                    "content": "Hello! How can I help?",
                    "sequence": 2,
                    "duration_ms": 500.0,
                },
            ],
        },
    )
    assert resp.status_code == 201, f"Events creation failed: {resp.text}"
    data = resp.json()
    assert len(data["events"]) == 3
    types = [e["event_type"] for e in data["events"]]
    assert "system_prompt" in types
    assert "prompt" in types
    assert "completion" in types


def test_create_log_with_error_fields(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "error",
            "message": "Something broke",
            "error_type": "ValueError",
            "error_message": "invalid input",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["level"] == "error"
    assert data["error_type"] == "ValueError"


def test_create_log_invalid_level_returns_400(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "banana",
            "message": "Invalid level test",
        },
    )
    assert resp.status_code == 400
    assert "log level" in resp.json()["detail"].lower()


def test_create_log_invalid_event_type_returns_400(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": "Invalid event type",
            "events": [{"event_type": "invalid_type", "content": "test"}],
        },
    )
    assert resp.status_code == 400
    assert "event type" in resp.json()["detail"].lower()


def test_create_log_missing_required_fields_returns_422(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={"service": "test-suite"},
    )
    assert resp.status_code == 422


def test_level_normalization_warning(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "WARNING",
            "message": "Warning level normalization test",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["level"] == "warn"


def test_level_normalization_critical(client, auth_headers):
    resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "CRITICAL",
            "message": "Critical level normalization test",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["level"] == "fatal"


def test_get_log_by_id(client, auth_headers):
    # Create a log
    create_resp = client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": "Log to retrieve by ID",
        },
    )
    log_id = create_resp.json()["id"]

    # Retrieve it
    resp = client.get(f"/v1/logs/{log_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == log_id
    assert resp.json()["message"] == "Log to retrieve by ID"


def test_get_nonexistent_log_returns_404(client, auth_headers):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/v1/logs/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_list_logs(client, auth_headers):
    resp = client.get("/v1/logs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "total" in data
    assert "page" in data
    assert "has_more" in data
    assert isinstance(data["logs"], list)


def test_list_logs_filter_by_service(client, auth_headers):
    resp = client.get(
        "/v1/logs", headers=auth_headers, params={"service": "test-suite"}
    )
    assert resp.status_code == 200
    for log in resp.json()["logs"]:
        assert log["service"] == "test-suite"


def test_list_logs_filter_by_level(client, auth_headers):
    resp = client.get(
        "/v1/logs", headers=auth_headers, params={"level": "error"}
    )
    assert resp.status_code == 200
    for log in resp.json()["logs"]:
        assert log["level"] == "error"


def test_list_logs_filter_has_error(client, auth_headers):
    resp = client.get(
        "/v1/logs", headers=auth_headers, params={"has_error": True}
    )
    assert resp.status_code == 200
    for log in resp.json()["logs"]:
        assert log["error_type"] is not None


def test_list_logs_pagination(client, auth_headers):
    resp = client.get(
        "/v1/logs", headers=auth_headers, params={"page_size": 2, "page": 1}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["logs"]) <= 2


def test_list_logs_search(client, auth_headers):
    # Create a log with a unique message
    unique = uuid.uuid4().hex[:8]
    client.post(
        "/v1/logs",
        headers=auth_headers,
        json={
            "service": "test-suite",
            "level": "info",
            "message": f"Unique search token {unique}",
        },
    )
    resp = client.get(
        "/v1/logs", headers=auth_headers, params={"search": unique}
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert unique in resp.json()["logs"][0]["message"]


def test_batch_create_logs(client, auth_headers):
    resp = client.post(
        "/v1/logs/batch",
        headers=auth_headers,
        json={
            "logs": [
                {
                    "service": "test-suite",
                    "level": "info",
                    "message": f"Batch log {i}",
                }
                for i in range(5)
            ]
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["accepted"] == 5
    assert data["failed"] == 0


def test_get_trace(client, auth_headers):
    tid = f"trace-test-{uuid.uuid4().hex[:8]}"
    # Create two logs with same trace_id
    for i in range(2):
        client.post(
            "/v1/logs",
            headers=auth_headers,
            json={
                "service": "test-suite",
                "level": "info",
                "message": f"Trace log {i}",
                "trace_id": tid,
                "span_id": f"span-{i}",
                "duration_ms": 100.0 * (i + 1),
            },
        )
    resp = client.get(f"/v1/logs/trace/{tid}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == tid
    assert len(data["logs"]) == 2
    assert "test-suite" in data["services"]


def test_get_nonexistent_trace_returns_404(client, auth_headers):
    resp = client.get(
        "/v1/logs/trace/nonexistent-trace-id", headers=auth_headers
    )
    assert resp.status_code == 404


def test_list_services(client, auth_headers):
    resp = client.get("/v1/logs/services", headers=auth_headers)
    assert resp.status_code == 200
    services = resp.json()
    assert isinstance(services, list)
    assert "test-suite" in services


def test_get_stats(client, auth_headers):
    resp = client.get("/v1/logs/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "by_level" in data
    assert "by_service" in data


def test_get_stats_filtered_by_service(client, auth_headers):
    resp = client.get(
        "/v1/logs/stats",
        headers=auth_headers,
        params={"service": "test-suite"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 0
