# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Integration tests for server startup and endpoint accessibility.
"""

from fastapi.testclient import TestClient


def test_server_startup(client: TestClient) -> None:
    """Test that the server starts and responds to requests."""
    response = client.get("/health", headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "pailflow"}


def test_health_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test the health check endpoint."""
    response = client.get("/health", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pailflow"


def test_workflows_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test the workflows listing endpoint."""
    response = client.get("/workflows", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "workflows" in data
    assert "count" in data
    assert isinstance(data["workflows"], list)
    assert isinstance(data["count"], int)
    assert data["count"] >= 0


def test_workflow_execution_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test the workflow execution endpoint."""
    response = client.post(
        "/workflow/code",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={
            "message": "test message",
            "user_id": "test-user",
            "channel_id": "test-channel",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_workflow_execution_missing_message(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test workflow execution with missing message."""
    response = client.post(
        "/workflow/code",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={},
    )
    assert response.status_code == 422  # Pydantic validation error


def test_workflow_execution_empty_message(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test workflow execution with empty message."""
    response = client.post(
        "/workflow/code",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": ""},
    )
    # Empty message should be rejected - either by Pydantic (422) or our validator (400)
    assert response.status_code in [400, 422]
    assert "detail" in response.json()


def test_workflow_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test workflow execution with non-existent workflow."""
    response = client.post(
        "/workflow/nonexistent",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": "test"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()
    assert "available" in data["detail"].lower()


def test_workflow_execution_long_message(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test workflow execution with message at max length."""
    long_message = "a" * 10000
    response = client.post(
        "/workflow/code",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": long_message},
    )
    assert response.status_code == 200


def test_workflow_execution_message_too_long(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test workflow execution with message exceeding max length."""
    too_long_message = "a" * 10001
    response = client.post(
        "/workflow/code",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": too_long_message},
    )
    assert response.status_code == 422  # Pydantic validation error
