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


@pytest.fixture
def sample_bot_config() -> dict:
    """Sample bot configuration for tests."""
    return {
        "bot_prompt": "You are a helpful AI assistant.",
        "name": "TestBot",
        "video_mode": "animated",
    }


@pytest.fixture
def sample_bot_request(sample_bot_config: dict) -> dict:
    """Sample bot join request payload for tests."""
    return {
        "provider": "daily",
        "room_url": "https://test.daily.co/test-room",
        "token": None,
        "bot_config": sample_bot_config,
        "process_insights": True,
    }


@pytest.fixture
def sample_bot_request_with_optional_fields(sample_bot_config: dict) -> dict:
    """Sample bot join request with all optional fields."""
    return {
        "provider": "daily",
        "room_url": "https://test.daily.co/test-room",
        "token": "test-token",
        "bot_config": sample_bot_config,
        "process_insights": True,
        "email": "test@example.com",
        "analysis_prompt": "Custom analysis prompt",
        "summary_format_prompt": "Custom summary format",
        "webhook_callback_url": "https://example.com/webhook",
    }


@pytest.fixture
def mock_bot_session() -> dict:
    """Mock bot session data for tests."""
    return {
        "bot_id": "550e8400-e29b-41d4-a716-446655440000",  # Valid UUID format
        "room_url": "https://test.daily.co/test-room",
        "room_name": "test-room",
        "status": "running",
        "started_at": "2025-01-15T10:00:00Z",
        "completed_at": None,
        "process_insights": True,
        "bot_config": {
            "bot_prompt": "You are a helpful AI assistant.",
            "name": "TestBot",
            "video_mode": "animated",
        },
        "transcript_text": None,
        "qa_pairs": None,
        "insights": None,
        "error": None,
    }


@pytest.fixture
def mock_completed_bot_session(mock_bot_session: dict) -> dict:
    """Mock completed bot session with results."""
    session = mock_bot_session.copy()
    session["status"] = "completed"
    session["completed_at"] = "2025-01-15T10:30:00Z"
    session["transcript_text"] = "This is a test transcript."
    session["qa_pairs"] = [
        {"question": "What is your name?", "answer": "My name is TestBot."}
    ]
    session["insights"] = {
        "summary": "Test summary",
        "key_points": ["Point 1", "Point 2"],
    }
    return session


@pytest.fixture
def mock_workflow_result() -> dict:
    """Mock workflow execution result."""
    return {
        "success": True,
        "thread_id": "test-thread-id",
    }


@pytest.fixture
def mock_session_data() -> dict:
    """Mock session data from rooms table."""
    return {
        "transcript_text": "This is a test transcript.",
        "qa_pairs": [
            {"question": "What is your name?", "answer": "My name is TestBot."}
        ],
        "insights": {"summary": "Test summary", "key_points": ["Point 1", "Point 2"]},
    }


@pytest.fixture(autouse=True)
def mock_unkey_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatically disable Unkey API verification for all tests."""
    # Simply unset UNKEY_ROOT_KEY to disable verification
    # The middleware will skip verification but we need to handle unkey_key_id
    monkeypatch.delenv("UNKEY_ROOT_KEY", raising=False)

    # Patch the middleware's verification block to set test key_id
    from shared.auth import unkey_middleware

    original_call = unkey_middleware.UnkeyAuthMiddleware.__call__

    async def patched_call(self, scope, receive, send):
        if scope["type"] != "http":
            await original_call(self, scope, receive, send)
            return

        from fastapi import Request

        request = Request(scope, receive=receive)

        # Let original middleware handle public routes and auth header checks
        # But we'll intercept after token extraction to set key_id
        auth_header = request.headers.get("authorization", "").strip()
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                # Set test key_id before calling original (which skips verification)
                if not hasattr(request.state, "unkey_key_id"):
                    request.state.unkey_key_id = "test-key-id"

        # Call original middleware
        await original_call(self, scope, receive, send)

    monkeypatch.setattr(unkey_middleware.UnkeyAuthMiddleware, "__call__", patched_call)
