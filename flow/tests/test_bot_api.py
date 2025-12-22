# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Unit tests for bot API endpoints with comprehensive mocking.

All tests use mocks to avoid:
- Real bot execution (expensive Daily.co operations)
- Real database operations
- Real workflow execution
- Real credit checking (external API calls)

All tests are fast, isolated unit tests.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestBotJoinEndpoint:
    """Tests for POST /v1/api/bot/join endpoint."""

    @patch("flow.main.check_credits_for_request")
    @patch("flow.db.save_workflow_thread_data")
    @patch("flow.db.get_workflow_thread_data")
    @patch("flow.main.save_bot_session")
    @patch("flow.workflows.bot_call.BotCallWorkflow")
    def test_join_bot_success_basic(
        self,
        mock_workflow_class: MagicMock,
        mock_save_bot_session: MagicMock,
        mock_get_workflow_thread_data: MagicMock,
        mock_save_workflow_thread_data: MagicMock,
        mock_check_credits: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        sample_bot_request: dict,
    ) -> None:
        """Test successful bot join with basic request."""
        # Setup mocks
        mock_check_credits.return_value = (True, None)
        mock_get_workflow_thread_data.return_value = None  # No existing thread
        mock_save_workflow_thread_data.return_value = True
        mock_save_bot_session.return_value = True

        mock_workflow_instance = MagicMock()
        mock_workflow_instance.execute_async = AsyncMock(
            return_value={"success": True, "thread_id": "test-thread-id"}
        )
        mock_workflow_class.return_value = mock_workflow_instance

        # Make request
        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=sample_bot_request,
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "bot_id" in data
        assert data["room_url"] == sample_bot_request["room_url"]
        assert uuid.UUID(data["bot_id"])  # Valid UUID

        # Verify mocks were called
        mock_check_credits.assert_called_once()
        mock_save_bot_session.assert_called_once()
        mock_workflow_instance.execute_async.assert_called_once()

    @patch("flow.main.check_credits_for_request")
    @patch("flow.db.save_workflow_thread_data")
    @patch("flow.db.get_workflow_thread_data")
    @patch("flow.main.save_bot_session")
    @patch("flow.workflows.bot_call.BotCallWorkflow")
    def test_join_bot_success_with_optional_fields(
        self,
        mock_workflow_class: MagicMock,
        mock_save_bot_session: MagicMock,
        mock_get_workflow_thread_data: MagicMock,
        mock_save_workflow_thread_data: MagicMock,
        mock_check_credits: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        sample_bot_request_with_optional_fields: dict,
    ) -> None:
        """Test successful bot join with all optional fields."""
        # Setup mocks
        mock_check_credits.return_value = (True, None)
        mock_get_workflow_thread_data.return_value = None
        mock_save_workflow_thread_data.return_value = True
        mock_save_bot_session.return_value = True

        mock_workflow_instance = MagicMock()
        mock_workflow_instance.execute_async = AsyncMock(
            return_value={"success": True, "thread_id": "test-thread-id"}
        )
        mock_workflow_class.return_value = mock_workflow_instance

        # Make request
        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=sample_bot_request_with_optional_fields,
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "bot_id" in data

    def test_join_bot_missing_room_url(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        sample_bot_config: dict,
    ) -> None:
        """Test bot join with missing room_url."""
        request = {
            "bot_config": sample_bot_config,
        }

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=request,
        )

        assert response.status_code == 422  # Validation error
        assert "detail" in response.json()

    def test_join_bot_missing_bot_config(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test bot join with missing bot_config."""
        request = {
            "room_url": "https://test.daily.co/test-room",
        }

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=request,
        )

        assert response.status_code == 422  # Validation error

    def test_join_bot_missing_bot_prompt(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test bot join with missing bot_prompt in bot_config."""
        request = {
            "room_url": "https://test.daily.co/test-room",
            "bot_config": {
                "name": "TestBot",
                "video_mode": "animated",
            },
        }

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=request,
        )

        assert response.status_code == 422  # Validation error

    @patch("flow.main.check_credits_for_request")
    def test_join_bot_static_mode_without_image(
        self,
        mock_check_credits: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test bot join with static video_mode but no static_image."""
        # Mock credit check to pass
        mock_check_credits.return_value = (True, None)

        request = {
            "room_url": "https://test.daily.co/test-room",
            "bot_config": {
                "bot_prompt": "You are a helpful assistant.",
                "name": "TestBot",
                "video_mode": "static",
                # Missing static_image
            },
        }

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=request,
        )

        assert response.status_code == 400
        data = response.json()
        assert "static_image" in data["detail"].lower()

    @patch("flow.main.check_credits_for_request")
    def test_join_bot_insufficient_credits(
        self,
        mock_check_credits: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        sample_bot_request: dict,
    ) -> None:
        """Test bot join with insufficient credits (402 error)."""
        # Setup mock to return insufficient credits
        mock_check_credits.return_value = (
            False,
            {
                "error": "insufficient_credits",
                "detail": "Your account has insufficient credits to perform this action.",
                "balance": 0.0,
                "message": "Please add credits to your account to continue.",
            },
        )

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=sample_bot_request,
        )

        assert response.status_code == 402
        data = response.json()
        assert data["error"] == "insufficient_credits"
        assert "balance" in data

    def test_join_bot_no_auth_header(
        self,
        client: TestClient,
        sample_bot_request: dict,
    ) -> None:
        """Test bot join without authentication header."""
        response = client.post(
            "/v1/api/bot/join",
            headers={},
            json=sample_bot_request,
        )

        assert response.status_code == 401

    def test_join_bot_invalid_auth_header(
        self,
        client: TestClient,
        sample_bot_request: dict,
    ) -> None:
        """Test bot join with invalid authentication header."""
        response = client.post(
            "/v1/api/bot/join",
            headers={"Authorization": "Bearer invalid-token"},
            json=sample_bot_request,
        )

        assert response.status_code == 401

    @patch("flow.main.check_credits_for_request")
    @patch("flow.db.save_workflow_thread_data")
    @patch("flow.db.get_workflow_thread_data")
    @patch("flow.main.save_bot_session")
    def test_join_bot_database_save_failure(
        self,
        mock_get_workflow_thread_data: MagicMock,
        mock_save_workflow_thread_data: MagicMock,
        mock_save_bot_session: MagicMock,
        mock_check_credits: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        sample_bot_request: dict,
    ) -> None:
        """Test bot join when database save fails."""
        # Setup mocks
        mock_check_credits.return_value = (True, None)
        mock_get_workflow_thread_data.return_value = None
        mock_save_workflow_thread_data.return_value = True
        mock_save_bot_session.return_value = False  # Database save fails

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=sample_bot_request,
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "database" in data["detail"].lower()

    @patch("flow.main.check_credits_for_request")
    @patch("flow.db.save_workflow_thread_data")
    @patch("flow.db.get_workflow_thread_data")
    @patch("flow.main.save_bot_session")
    @patch("flow.workflows.bot_call.BotCallWorkflow")
    def test_join_bot_workflow_execution_failure(
        self,
        mock_workflow_class: MagicMock,
        mock_save_bot_session: MagicMock,
        mock_get_workflow_thread_data: MagicMock,
        mock_save_workflow_thread_data: MagicMock,
        mock_check_credits: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        sample_bot_request: dict,
    ) -> None:
        """Test bot join when workflow execution fails."""
        # Setup mocks
        mock_check_credits.return_value = (True, None)
        mock_get_workflow_thread_data.return_value = None
        mock_save_workflow_thread_data.return_value = True
        mock_save_bot_session.return_value = True

        mock_workflow_instance = MagicMock()
        mock_workflow_instance.execute_async = AsyncMock(
            return_value={"success": False, "error": "Workflow execution failed"}
        )
        mock_workflow_class.return_value = mock_workflow_instance

        response = client.post(
            "/v1/api/bot/join",
            headers=auth_headers,
            json=sample_bot_request,
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

        # Verify bot session was updated with failure
        assert mock_save_bot_session.call_count >= 2  # Initial save + failure update


class TestBotStatusEndpoint:
    """Tests for GET /v1/api/bot/{bot_id}/status endpoint."""

    @patch("flow.main.bot_service")
    @patch("flow.main.get_bot_session")
    def test_get_bot_status_running(
        self,
        mock_get_bot_session: MagicMock,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_bot_session: dict,
    ) -> None:
        """Test getting status for a running bot."""
        # Setup mocks
        mock_get_bot_session.return_value = mock_bot_session
        mock_bot_service.is_bot_running.return_value = True

        response = client.get(
            f"/v1/api/bot/{mock_bot_session['bot_id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["bot_id"] == mock_bot_session["bot_id"]
        assert data["room_url"] == mock_bot_session["room_url"]
        assert data["started_at"] == mock_bot_session["started_at"]
        assert data["completed_at"] is None

    @patch("flow.main.bot_service")
    @patch("flow.main.get_bot_session")
    @patch("flow.db.get_session_data")
    @patch("flow.main.save_bot_session")
    def test_get_bot_status_completed(
        self,
        mock_save_bot_session: MagicMock,
        mock_get_session_data: MagicMock,
        mock_get_bot_session: MagicMock,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_bot_session: dict,
        mock_session_data: dict,
    ) -> None:
        """Test getting status for a completed bot."""
        # Setup mocks
        session = mock_bot_session.copy()
        session["status"] = "running"  # Initially running
        mock_get_bot_session.return_value = session
        mock_bot_service.is_bot_running.return_value = False  # Bot finished
        mock_get_session_data.return_value = mock_session_data
        mock_save_bot_session.return_value = True

        response = client.get(
            f"/v1/api/bot/{session['bot_id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["transcript"] == mock_session_data["transcript_text"]
        assert data["qa_pairs"] == mock_session_data["qa_pairs"]
        assert data["insights"] == mock_session_data["insights"]

    @patch("flow.main.bot_service")
    @patch("flow.main.get_bot_session")
    @patch("flow.db.get_session_data")
    @patch("flow.main.save_bot_session")
    def test_get_bot_status_completed_with_results(
        self,
        mock_save_bot_session: MagicMock,
        mock_get_session_data: MagicMock,
        mock_get_bot_session: MagicMock,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_completed_bot_session: dict,
    ) -> None:
        """Test getting status for a completed bot with all results."""
        # Setup mocks
        mock_get_bot_session.return_value = mock_completed_bot_session
        mock_bot_service.is_bot_running.return_value = False
        mock_get_session_data.return_value = None  # Already in session
        mock_save_bot_session.return_value = True

        response = client.get(
            f"/v1/api/bot/{mock_completed_bot_session['bot_id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["transcript"] is not None
        assert data["qa_pairs"] is not None
        assert data["insights"] is not None
        assert data["completed_at"] is not None

    @patch("flow.steps.agent_call.bot.bot_service.bot_service")
    @patch("flow.db.get_bot_session")
    def test_get_bot_status_not_found(
        self,
        mock_get_bot_session: MagicMock,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting status for non-existent bot."""
        # Setup mocks
        mock_get_bot_session.return_value = None

        response = client.get(
            "/v1/api/bot/non-existent-bot-id/status",
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @patch("flow.main.bot_service")
    @patch("flow.main.get_bot_session")
    def test_get_bot_status_failed(
        self,
        mock_get_bot_session: MagicMock,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_bot_session: dict,
    ) -> None:
        """Test getting status for a failed bot."""
        # Setup mocks
        session = mock_bot_session.copy()
        session["status"] = "failed"
        session["error"] = "Bot execution failed"
        mock_get_bot_session.return_value = session
        mock_bot_service.is_bot_running.return_value = False

        response = client.get(
            f"/v1/api/bot/{session['bot_id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Bot execution failed"

    @patch("flow.main.bot_service")
    @patch("flow.main.get_bot_session")
    @patch("flow.db.get_session_data")
    @patch("flow.main.save_bot_session")
    def test_get_bot_status_updates_during_request(
        self,
        mock_save_bot_session: MagicMock,
        mock_get_session_data: MagicMock,
        mock_get_bot_session: MagicMock,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
        mock_bot_session: dict,
        mock_session_data: dict,
    ) -> None:
        """Test status update when bot finishes during request."""
        # Setup mocks - bot was running but finishes during request
        session = mock_bot_session.copy()
        session["status"] = "running"
        mock_get_bot_session.return_value = session
        mock_bot_service.is_bot_running.return_value = False  # Bot finished
        mock_get_session_data.return_value = mock_session_data
        mock_save_bot_session.return_value = True

        response = client.get(
            f"/v1/api/bot/{session['bot_id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Status should be updated to completed
        assert data["status"] == "completed"
        # Verify session was saved with updated status
        assert mock_save_bot_session.called


class TestOtherBotEndpoints:
    """Tests for other bot management endpoints."""

    @patch("flow.steps.agent_call.bot_service")
    def test_get_all_bots_status(
        self,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting status of all active bots."""
        # Setup mocks - bot_service is imported inside the function
        mock_bot_service.list_active_bots.return_value = {
            "room-1": {
                "room_name": "room-1",
                "runtime_hours": 0.5,
            },
            "room-2": {
                "room_name": "room-2",
                "runtime_hours": 1.5,
            },
        }

        response = client.get("/v1/bots/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_active_bots" in data
        assert "total_runtime_hours" in data
        assert "long_running_bots" in data
        assert "bots" in data
        assert data["total_active_bots"] == 2

    @patch("flow.steps.agent_call.bot_service")
    def test_cleanup_bots(
        self,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cleanup of long-running bots."""
        # Setup mocks - bot_service is imported inside the function
        mock_bot_service.cleanup_long_running_bots = AsyncMock(return_value=2)

        response = client.post(
            "/v1/bots/cleanup?max_hours=2.0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["bots_stopped"] == 2
        assert data["max_hours"] == 2.0

    @patch("flow.steps.agent_call.bot_service")
    def test_stop_bot_for_room(
        self,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test stopping bot for a specific room."""
        # Setup mocks - bot_service is imported inside the function
        mock_bot_service.stop_bot = AsyncMock(return_value=True)

        response = client.post(
            "/v1/bots/stop/test-room",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["room_name"] == "test-room"

    @patch("flow.steps.agent_call.bot_service")
    def test_stop_bot_for_room_not_found(
        self,
        mock_bot_service: MagicMock,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test stopping bot for non-existent room."""
        # Setup mocks - bot_service is imported inside the function
        mock_bot_service.stop_bot = AsyncMock(return_value=False)

        response = client.post(
            "/v1/bots/stop/non-existent-room",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_found"
        assert data["room_name"] == "non-existent-room"
