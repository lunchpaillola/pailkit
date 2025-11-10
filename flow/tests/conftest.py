# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test configuration and fixtures for PailFlow integration tests.
"""

import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from flow.main import app

# Load environment variables
load_dotenv()

# Test authentication token (can be overridden via environment)
TEST_AUTH_TOKEN = os.getenv("TEST_AUTH_TOKEN", "test-key")


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Create authentication headers for test requests."""
    return {"Authorization": f"Bearer {TEST_AUTH_TOKEN}"}
