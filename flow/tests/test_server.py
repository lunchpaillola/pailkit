# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Unit tests for server startup and health check endpoint.
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
