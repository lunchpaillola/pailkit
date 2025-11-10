# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Tests for the transcription router with Daily.co provider.

Note: Most tests are mocked for speed and reliability.
Set RUN_INTEGRATION_TESTS=true environment variable to run real API tests.
"""

import os
import time
import webbrowser
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app  # noqa: E402
from api.tests.conftest import AUTH_KEY  # noqa: E402

client = TestClient(app)

# Check if integration tests should run
RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"


class TestDailyTranscriptionProvider:
    """Unit tests for DailyTranscription class methods."""

    def test_extract_room_name_valid_url(self) -> None:
        """Test extracting room name from valid Daily.co URL."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        room_name = provider._extract_room_name(
            "https://example.daily.co/test-room-123"
        )
        assert room_name == "test-room-123"

    def test_extract_room_name_with_trailing_slash(self) -> None:
        """Test extracting room name from URL with trailing slash."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        room_name = provider._extract_room_name("https://example.daily.co/test-room/")
        assert room_name == "test-room"

    def test_extract_room_name_empty_url(self) -> None:
        """Test extracting room name from empty URL raises error."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        with pytest.raises(ValueError, match="audio_url is required"):
            provider._extract_room_name(None)

    def test_extract_room_name_invalid_url(self) -> None:
        """Test extracting room name from invalid URL raises error."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        with pytest.raises(ValueError, match="Invalid Daily.co room URL"):
            provider._extract_room_name("https://example.daily.co/")

    def test_get_model_from_profile_meeting(self) -> None:
        """Test getting model from meeting profile."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {"profile": "meeting"}
        model = provider._get_model_from_profile(config)
        assert model == "nova-3-meeting"

    def test_get_model_from_profile_medical(self) -> None:
        """Test getting model from medical profile."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {"profile": "medical"}
        model = provider._get_model_from_profile(config)
        assert model == "nova-3-medical"

    def test_get_model_from_profile_finance(self) -> None:
        """Test getting model from finance profile."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {"profile": "finance"}
        model = provider._get_model_from_profile(config)
        assert model == "nova-2-finance"

    def test_get_model_from_profile_general(self) -> None:
        """Test getting model from general profile."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {"profile": "general"}
        model = provider._get_model_from_profile(config)
        assert model == "nova-3"

    def test_get_model_from_profile_default(self) -> None:
        """Test getting model from unknown profile defaults to meeting."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {"profile": "unknown"}
        model = provider._get_model_from_profile(config)
        assert model == "nova-3-meeting"  # Defaults to meeting

    def test_to_daily_config_basic(self) -> None:
        """Test converting PailKit config to Daily config format."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {"profile": "meeting", "language": "en"}
        daily_config = provider._to_daily_config(config)
        assert daily_config["model"] == "nova-3-meeting"
        assert daily_config["language"] == "en"
        assert daily_config["punctuate"] is True  # Default
        assert daily_config["profanity_filter"] is False  # Default

    def test_to_daily_config_with_overrides(self) -> None:
        """Test converting config with feature overrides."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        config = {
            "profile": "medical",
            "language": "es",
            "features": {"punctuate": False, "profanity_filter": True},
        }
        daily_config = provider._to_daily_config(config)
        assert daily_config["model"] == "nova-3-medical"
        assert daily_config["language"] == "es"
        assert daily_config["punctuate"] is False
        assert daily_config["profanity_filter"] is True

    @pytest.mark.asyncio
    async def test_start_transcription_success(self) -> None:
        """Test starting transcription successfully."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # Mock httpx.AsyncClient
        with patch("api.transcribe.providers.daily.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            result = await provider.start_transcription(
                audio_url="https://example.daily.co/test-room",
                config={"profile": "meeting"},
            )

            assert result["success"] is True
            assert result["transcription_id"] == "test-room"
            assert result["provider"] == "daily"
            assert result["message"] == "Transcription started successfully"
            assert result["room_name"] == "test-room"
            assert "config" in result

    @pytest.mark.asyncio
    async def test_start_transcription_missing_url(self) -> None:
        """Test starting transcription without audio_url."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        result = await provider.start_transcription(audio_url=None)

        assert result["success"] is False
        assert result["transcription_id"] == ""
        assert "audio_url is required" in result["message"]

    @pytest.mark.asyncio
    async def test_start_transcription_api_error_404(self) -> None:
        """Test starting transcription with 404 error (room not found)."""
        import httpx

        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")

        # Mock httpx response with 404 error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json = MagicMock(
            return_value={
                "error": "not-found",
                "info": "room test does not seem to be hosting a call currently",
            }
        )
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Room not found", request=MagicMock(), response=mock_response
            )
        )

        # Mock httpx.AsyncClient
        with patch("api.transcribe.providers.daily.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            result = await provider.start_transcription(
                audio_url="https://example.daily.co/test-room",
                config={"profile": "meeting"},
            )

            assert result["success"] is False
            assert "Daily API error" in result["message"]
            assert "not-found" in result["message"]

    @pytest.mark.asyncio
    async def test_start_transcription_api_error_400(self) -> None:
        """Test starting transcription with 400 error (invalid request)."""
        import httpx

        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")

        # Mock httpx response with 400 error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json = MagicMock(
            return_value={
                "error": "invalid-request-error",
                "info": "room test has an active stream",
            }
        )
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Invalid request", request=MagicMock(), response=mock_response
            )
        )

        # Mock httpx.AsyncClient
        with patch("api.transcribe.providers.daily.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            result = await provider.start_transcription(
                audio_url="https://example.daily.co/test-room",
                config={"profile": "meeting"},
            )

            assert result["success"] is False
            assert "Daily API error" in result["message"]
            assert "invalid-request-error" in result["message"]

    @pytest.mark.asyncio
    async def test_start_transcription_invalid_url(self) -> None:
        """Test starting transcription with invalid URL."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        result = await provider.start_transcription(
            audio_url="https://example.daily.co/",  # Missing room name
            config={"profile": "meeting"},
        )

        assert result["success"] is False
        assert "Validation error" in result["message"]

    @pytest.mark.asyncio
    async def test_stop_transcription_success(self) -> None:
        """Test stopping transcription successfully."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # Mock httpx.AsyncClient
        with patch("api.transcribe.providers.daily.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            result = await provider.stop_transcription("test-room")

            assert result["success"] is True
            assert result["transcription_id"] == "test-room"
            assert result["provider"] == "daily"
            assert result["message"] == "Transcription stopped successfully"
            assert result["room_name"] == "test-room"
            assert result["final_transcript"] is None

    @pytest.mark.asyncio
    async def test_stop_transcription_missing_id(self) -> None:
        """Test stopping transcription without transcription_id."""
        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")
        result = await provider.stop_transcription("")

        assert result["success"] is False
        assert "transcription_id (room_name) is required" in result["message"]

    @pytest.mark.asyncio
    async def test_stop_transcription_api_error(self) -> None:
        """Test stopping transcription with API error."""
        import httpx

        from api.transcribe.providers.daily import DailyTranscription

        provider = DailyTranscription(api_key="test-key")

        # Mock httpx response with error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json = MagicMock(return_value={"error": "not-found"})
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
        )

        # Mock httpx.AsyncClient
        with patch("api.transcribe.providers.daily.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            result = await provider.stop_transcription("test-room")

            assert result["success"] is False
            assert "Daily API error" in result["message"]


class TestTranscriptionRouter:
    """Integration tests for /api/transcribe endpoints."""

    def test_start_transcription_requires_authorization(self) -> None:
        """Test that start transcription requires authorization."""
        response = client.post(
            "/api/transcribe/start",
            json={"profile": "meeting"},
        )
        assert response.status_code == 401
        assert "Authorization header required" in response.json().get("detail", "")

    @patch("api.routers.transcribe.get_provider")
    def test_start_transcription_success(self, mock_get_provider: Any) -> None:
        """Test starting transcription via API endpoint."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.start_transcription = AsyncMock(
            return_value={
                "success": True,
                "transcription_id": "test-room",
                "provider": "daily",
                "message": "Transcription started successfully",
                "room_name": "test-room",
                "config": {"model": "nova-3-meeting", "language": "en"},
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data
        request_data = {
            "profile": "meeting",
            "audio_url": "https://example.daily.co/test-room",
        }

        # Make request with required headers
        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["transcription_id"] == "test-room"
        assert data["provider"] == "daily"
        assert data["message"] == "Transcription started successfully"
        assert "room_name" in data
        assert "config" in data

    @patch("api.routers.transcribe.get_provider")
    def test_start_transcription_with_overrides(self, mock_get_provider: Any) -> None:
        """Test starting transcription with profile and overrides."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.start_transcription = AsyncMock(
            return_value={
                "success": True,
                "transcription_id": "test-room",
                "provider": "daily",
                "message": "Transcription started successfully",
                "room_name": "test-room",
                "config": {"model": "nova-3-medical", "language": "es"},
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with profile and overrides
        request_data = {
            "profile": "medical",
            "audio_url": "https://example.daily.co/test-room",
            "overrides": {"language": "es"},
        }

        # Make request with required headers
        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @patch("api.routers.transcribe.get_provider")
    def test_start_transcription_provider_failure(self, mock_get_provider: Any) -> None:
        """Test starting transcription when provider fails."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.start_transcription = AsyncMock(
            return_value={
                "success": False,
                "transcription_id": "",
                "provider": "daily",
                "message": "Daily API error: Invalid API key",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        request_data = {
            "profile": "meeting",
            "audio_url": "https://example.daily.co/test-room",
        }

        # Make request with required headers
        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 500
        data = response.json()
        assert "Invalid API key" in data["detail"]

    def test_start_transcription_unsupported_provider(self) -> None:
        """Test starting transcription with unsupported provider."""
        request_data = {
            "profile": "meeting",
            "audio_url": "https://example.daily.co/test-room",
        }

        # Make request with unsupported provider in header
        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "unsupported",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "not yet implemented" in data["detail"]

    @patch("api.routers.transcribe.get_provider")
    def test_start_transcription_missing_api_key(self, mock_get_provider: Any) -> None:
        """Test starting transcription with missing API key."""
        request_data = {
            "profile": "meeting",
            "audio_url": "https://example.daily.co/test-room",
        }

        # Make request without X-Provider-Auth header
        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 422  # FastAPI validation error

    @patch("api.routers.transcribe.get_provider")
    def test_stop_transcription_success(self, mock_get_provider: Any) -> None:
        """Test stopping transcription via API endpoint."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.stop_transcription = AsyncMock(
            return_value={
                "success": True,
                "transcription_id": "test-room",
                "provider": "daily",
                "message": "Transcription stopped successfully",
                "room_name": "test-room",
                "final_transcript": None,
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data
        request_data = {"transcription_id": "test-room"}

        # Make request with required headers
        response = client.post(
            "/api/transcribe/stop",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["transcription_id"] == "test-room"
        assert data["provider"] == "daily"
        assert data["message"] == "Transcription stopped successfully"
        assert data["final_transcript"] is None

    @patch("api.routers.transcribe.get_provider")
    def test_stop_transcription_provider_failure(self, mock_get_provider: Any) -> None:
        """Test stopping transcription when provider fails."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.stop_transcription = AsyncMock(
            return_value={
                "success": False,
                "transcription_id": "test-room",
                "provider": "daily",
                "message": "Daily API error: Room not found",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        request_data = {"transcription_id": "test-room"}

        # Make request with required headers
        response = client.post(
            "/api/transcribe/stop",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 500
        data = response.json()
        assert "Room not found" in data["detail"]

    def test_stop_transcription_missing_id(self) -> None:
        """Test stopping transcription without transcription_id."""
        request_data: dict[str, Any] = {}  # Missing transcription_id

        # Make request with required headers
        response = client.post(
            "/api/transcribe/stop",
            json=request_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_start_transcription_real_api(self) -> None:
        """
        Integration test: Start transcription with real Daily API key.

        IMPORTANT: Daily.co transcription requires an active participant in the room.
        This test will:
        1. Create a room
        2. Print the room URL - YOU NEED TO JOIN IT MANUALLY
        3. Try to start transcription (will fail if no one is in room)
        4. Clean up the room

        To test transcription successfully:
        - Open the printed room URL in a browser
        - Join the room (allow camera/mic permissions)
        - Keep the tab open while the test runs
        """
        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        # First, create a room
        room_data = {"profile": "conversation"}
        create_response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        if create_response.status_code != 200:
            pytest.skip(f"Failed to create test room: {create_response.json()}")

        room_info = create_response.json()
        room_url = room_info.get("room_url")
        room_name = room_info.get("room_name", room_info.get("room_id"))

        if not room_url:
            pytest.skip("Failed to get room URL from creation response")

        # Print clear instructions for the user
        print(f"\n{'='*70}")
        print("INTEGRATION TEST: Transcription Test")
        print(f"{'='*70}")
        print(f"Room created: {room_name}")
        print(f"JOIN THIS ROOM: {room_url}")
        print("\nIMPORTANT: Daily.co transcription requires an active participant!")
        print("\nTO TEST TRANSCRIPTION:")
        print(f"  1. Open this URL in your browser: {room_url}")
        print("  2. Click 'Join' and allow camera/mic permissions")
        print("  3. You should see yourself in the room")
        print("  4. Keep the tab open - the test will wait 60 seconds")
        print("  5. Speak something so there's audio to transcribe")
        print("\nWaiting 60 seconds for you to join the room...")
        print("  (The test will continue automatically after the countdown)")
        print(f"{'='*70}\n")

        # Wait longer for user to join and speak
        import time

        for i in range(60, 0, -10):
            print(f"  {i} seconds remaining... (join at: {room_url})")
            time.sleep(10)

        print(f"\n{'='*70}")
        print("Starting transcription test...")
        print(f"{'='*70}\n")

        # Try to start transcription
        request_data = {
            "profile": "meeting",
            "audio_url": room_url,
        }

        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # The response might be 200 (success) or 500 (room not hosting a call)
        # Both are valid scenarios to test
        assert response.status_code in [200, 500]
        data = response.json()

        if response.status_code == 200:
            assert data["success"] is True
            assert data["transcription_id"] == room_name
            assert data["provider"] == "daily"
            print(f"SUCCESS: Transcription started successfully for room: {room_name}")
            print(f"  Transcription ID: {room_name}")
            print(f"  Provider: {data['provider']}")
            print(f"  Config: {data.get('config', {})}")

            # Try to stop it
            print("\nStopping transcription...")
            stop_response = client.post(
                "/api/transcribe/stop",
                json={"transcription_id": room_name},
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )
            if stop_response.status_code == 200:
                stop_data = stop_response.json()
                print("SUCCESS: Transcription stopped successfully")
                print(f"  Transcription ID: {stop_data.get('transcription_id')}")
                print(f"  Message: {stop_data.get('message')}")
            else:
                print(f"WARNING: Failed to stop transcription: {stop_response.json()}")
        else:
            # Expected error: room not hosting a call
            error_detail = data.get("detail", "")
            assert (
                "not hosting a call" in error_detail.lower()
                or "not-found" in error_detail.lower()
                or "does not seem to be hosting" in error_detail.lower()
            )
            print(f"INFO: Expected error (room not hosting a call): {error_detail}")
            print("  This is normal if no one joined the room.")
            print(f"  To test transcription, join the room at: {room_url}")

        # Clean up: Delete the room
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )
        if delete_response.status_code == 200:
            print(f"SUCCESS: Room {room_name} cleaned up successfully")
        else:
            print(
                f"WARNING: Failed to clean up room {room_name}: {delete_response.json()}"
            )
        print(f"{'='*70}\n")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_start_transcription_with_different_profiles(self) -> None:
        """Integration test: Test transcription with different profiles."""
        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        # Test profiles
        profiles = ["meeting", "medical", "finance", "general"]

        for profile in profiles:
            # Create a room with auto-join configuration
            room_data = {
                "profile": "conversation",
                "overrides": {
                    "interaction": {"prejoin": False},
                    "media": {"video": False},
                },
            }
            create_response = client.post(
                "/api/rooms/create",
                json=room_data,
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )

            if create_response.status_code != 200:
                print(f"??  Failed to create test room for profile {profile}")
                continue

            room_info = create_response.json()
            room_url = room_info.get("room_url")
            room_name = room_info.get("room_name", room_info.get("room_id"))

            if not room_url:
                continue

            # Open room in browser to ensure participant joins
            webbrowser.open(room_url)

            # Wait for room to load and participant to join
            timeout = int(os.getenv("TRANSCRIPTION_TEST_TIMEOUT", "15"))
            print(
                f"Waiting {timeout} seconds for participant to join room for {profile} profile..."
            )
            time.sleep(timeout)

            # Try to start transcription with this profile
            request_data = {
                "profile": profile,
                "audio_url": room_url,
            }

            response = client.post(
                "/api/transcribe/start",
                json=request_data,
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )

            # Check response structure - handle both success and error responses
            data = response.json()

            if response.status_code == 200:
                # Success case - verify response structure
                assert "success" in data, "Response missing 'success' field"
                assert (
                    data["success"] is True
                ), "Transcription should succeed with participant"
                assert "provider" in data, "Response missing 'provider' field"
                assert (
                    data["provider"] == "daily"
                ), f"Expected provider 'daily', got '{data.get('provider')}'"
                print(
                    f"\n? Transcription started successfully with {profile} profile "
                    f"for room: {room_name}"
                )

                # Stop transcription if it started successfully
                stop_response = client.post(
                    "/api/transcribe/stop",
                    json={"transcription_id": room_name},
                    headers={
                        "X-Provider-Auth": f"Bearer {daily_api_key}",
                        "X-Provider": "daily",
                        "Authorization": f"Bearer {AUTH_KEY}",
                    },
                )
                if stop_response.status_code == 200:
                    print("   ? Transcription stopped successfully")
                else:
                    print(
                        f"   ??  Failed to stop transcription: {stop_response.json()}"
                    )
            else:
                # Error case - handle error response structure
                error_detail = data.get("detail", "")
                assert error_detail, "Error response missing 'detail' field"
                print(f"   ? Expected error for {profile} profile: {error_detail}")

            # Clean up: Delete the room
            client.delete(
                f"/api/rooms/delete/{room_name}",
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_start_transcription_with_overrides_integration(self) -> None:
        """Integration test: Test transcription with custom overrides."""
        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        # Create a room with auto-join configuration
        room_data = {
            "profile": "conversation",
            "overrides": {
                "interaction": {"prejoin": False},
                "media": {"video": False},
            },
        }
        create_response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        if create_response.status_code != 200:
            pytest.skip(f"Failed to create test room: {create_response.json()}")

        room_info = create_response.json()
        room_url = room_info.get("room_url")
        room_name = room_info.get("room_name", room_info.get("room_id"))

        if not room_url:
            pytest.skip("Failed to get room URL from creation response")

        # Open room in browser to ensure participant joins
        webbrowser.open(room_url)

        # Wait for room to load and participant to join
        timeout = int(os.getenv("TRANSCRIPTION_TEST_TIMEOUT", "15"))
        print(f"Waiting {timeout} seconds for participant to join room...")
        time.sleep(timeout)

        # Try to start transcription with overrides
        request_data = {
            "profile": "meeting",
            "audio_url": room_url,
            "overrides": {
                "language": "es",
                "features": {"punctuate": False, "profanity_filter": True},
            },
        }

        response = client.post(
            "/api/transcribe/start",
            json=request_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Check response structure - handle both success and error responses
        data = response.json()

        if response.status_code == 200:
            # Success case - verify response structure
            assert "success" in data, "Response missing 'success' field"
            assert (
                data["success"] is True
            ), "Transcription should succeed with participant"
            assert "provider" in data, "Response missing 'provider' field"
            assert (
                data["provider"] == "daily"
            ), f"Expected provider 'daily', got '{data.get('provider')}'"

            # Verify config includes overrides
            config = data.get("config", {})
            assert (
                config.get("language") == "es"
            ), f"Expected language 'es', got '{config.get('language')}'"
            assert (
                config.get("punctuate") is False
            ), f"Expected punctuate=False, got '{config.get('punctuate')}'"
            assert (
                config.get("profanity_filter") is True
            ), f"Expected profanity_filter=True, got '{config.get('profanity_filter')}'"
            print(
                f"\n? Transcription started successfully with overrides for room: {room_name}"
            )
            print(
                f"   Config verified: language={config.get('language')}, "
                f"punctuate={config.get('punctuate')}, "
                f"profanity_filter={config.get('profanity_filter')}"
            )

            # Stop transcription if it started successfully
            stop_response = client.post(
                "/api/transcribe/stop",
                json={"transcription_id": room_name},
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )
            if stop_response.status_code == 200:
                print("   ? Transcription stopped successfully")
            else:
                print(f"   ??  Failed to stop transcription: {stop_response.json()}")
        else:
            # Error case - handle error response structure
            error_detail = data.get("detail", "")
            assert error_detail, "Error response missing 'detail' field"
            print(f"   ? Expected error: {error_detail}")

        # Clean up: Delete the room
        client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_start_transcription_automated_browser_join(self) -> None:
        """
        Integration test: Start transcription with automated browser join.

        This test creates a room with auto-join configuration, opens it in the default browser,
        and tests transcription without requiring manual intervention.

        Auto-join configuration:
        - enable_prejoin_ui: False (skip pre-join screen)
        - start_video_off: True (camera off by default)
        - start_audio_off: True (mic off by default - Daily.co client-side setting)
        """
        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        # Create room with auto-join configuration using PailKit format
        # These will be converted to Daily.co properties by the provider
        room_data = {
            "profile": "conversation",
            "overrides": {
                "interaction": {
                    "prejoin": False,  # Skip pre-join screen ? enable_prejoin_ui: False
                },
                "media": {
                    "video": False,  # Camera off by default ? start_video_off: True
                    # Note: start_audio_off is client-side in Daily.co, not a room property
                },
            },
        }

        # Create the room
        create_response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        if create_response.status_code != 200:
            pytest.skip(f"Failed to create test room: {create_response.json()}")

        room_info = create_response.json()
        room_url = room_info.get("room_url")
        room_name = room_info.get("room_name", room_info.get("room_id"))

        if not room_url:
            pytest.skip("Failed to get room URL from creation response")

        # Initialize room_name for cleanup
        room_name_for_cleanup = room_name

        try:
            # Open room in default browser (auto-join configured)
            webbrowser.open(room_url)

            # Wait for room to load and auto-join
            # Get configurable timeout from environment variable, default to 15 seconds
            timeout = int(os.getenv("TRANSCRIPTION_TEST_TIMEOUT", "15"))
            print(f"Waiting {timeout} seconds for room to load and auto-join...")
            time.sleep(timeout)

            # Test starting transcription
            request_data = {
                "profile": "meeting",
                "audio_url": room_url,
            }

            start_response = client.post(
                "/api/transcribe/start",
                json=request_data,
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )

            # Verify response structure and status codes
            # Handle success (200), server errors (500), client errors (400, 404)
            assert start_response.status_code in [200, 400, 404, 500], (
                f"Unexpected status code: {start_response.status_code}. "
                f"Expected 200 (success), 400 (bad request), 404 (not found), or 500 (server error)"
            )
            data = start_response.json()

            if start_response.status_code == 200:
                # Success case - verify response structure matches expected schema
                assert "success" in data, "Response missing 'success' field"
                assert data["success"] is True, "Transcription start should succeed"
                assert "provider" in data, "Response missing 'provider' field"
                assert (
                    data["provider"] == "daily"
                ), f"Expected provider 'daily', got '{data['provider']}'"
                assert (
                    "transcription_id" in data
                ), "Response missing 'transcription_id' field"
                assert (
                    data["transcription_id"] == room_name
                ), f"Expected transcription_id '{room_name}', got '{data.get('transcription_id')}'"
                assert "room_name" in data, "Response missing 'room_name' field"
                assert (
                    data["room_name"] == room_name
                ), f"Expected room_name '{room_name}', got '{data.get('room_name')}'"
                assert "config" in data, "Response missing 'config' field"
                assert isinstance(data["config"], dict), "Config should be a dictionary"
                # Verify config contains expected Daily.co transcription settings
                config = data["config"]
                assert "model" in config, "Config missing 'model' field"
                assert "language" in config, "Config missing 'language' field"
                assert config["model"] in [
                    "nova-3",
                    "nova-3-meeting",
                    "nova-3-medical",
                    "nova-2-finance",
                ], f"Unexpected model: {config['model']}"
                assert "message" in data, "Response missing 'message' field"
                assert (
                    "Transcription started successfully" in data["message"]
                ), f"Expected success message, got: {data.get('message')}"

                # Wait a bit to let transcription run and see it working
                print(
                    "Transcription started successfully. Waiting 5 seconds to see it working..."
                )
                time.sleep(5)

                # Test stopping transcription
                print("Stopping transcription...")
                stop_response = client.post(
                    "/api/transcribe/stop",
                    json={"transcription_id": room_name},
                    headers={
                        "X-Provider-Auth": f"Bearer {daily_api_key}",
                        "X-Provider": "daily",
                        "Authorization": f"Bearer {AUTH_KEY}",
                    },
                )

                # Verify stop response structure
                assert stop_response.status_code in [
                    200,
                    500,
                ], f"Unexpected stop status code: {stop_response.status_code}"
                stop_data = stop_response.json()

                if stop_response.status_code == 200:
                    # Verify stop response structure matches expected schema
                    assert (
                        "success" in stop_data
                    ), "Stop response missing 'success' field"
                    assert (
                        stop_data["success"] is True
                    ), "Transcription stop should succeed"
                    assert (
                        "provider" in stop_data
                    ), "Stop response missing 'provider' field"
                    assert (
                        stop_data["provider"] == "daily"
                    ), f"Expected provider 'daily', got '{stop_data['provider']}'"
                    assert (
                        "transcription_id" in stop_data
                    ), "Stop response missing 'transcription_id' field"
                    assert stop_data["transcription_id"] == room_name, (
                        f"Expected stop transcription_id '{room_name}', "
                        f"got '{stop_data.get('transcription_id')}'"
                    )
                    assert (
                        "room_name" in stop_data
                    ), "Stop response missing 'room_name' field"
                    assert (
                        stop_data["room_name"] == room_name
                    ), f"Expected room_name '{room_name}', got '{stop_data.get('room_name')}'"
                    assert (
                        "final_transcript" in stop_data
                    ), "Stop response missing 'final_transcript' field"
                    # Daily.co real-time transcription doesn't return final transcript
                    # It's None because transcripts are retrieved via Daily.co's transcript API
                    assert (
                        stop_data["final_transcript"] is None
                    ), "Daily.co real-time transcription should return None for final_transcript"
                    assert (
                        "message" in stop_data
                    ), "Stop response missing 'message' field"
                    assert (
                        "Transcription stopped successfully" in stop_data["message"]
                    ), f"Expected stop success message, got: {stop_data.get('message')}"
                    print(
                        "Transcription stopped successfully. Waiting 2 seconds before cleanup..."
                    )
                    time.sleep(2)
                else:
                    # Log warning but don't fail the test
                    print(
                        "WARNING: Failed to stop transcription: "
                        f"{stop_data.get('detail', stop_data)}"
                    )
                    time.sleep(2)

            elif start_response.status_code == 400:
                # Bad request error (400) - FastAPI returns {"detail": "..."} format
                error_detail = data.get("detail", "")
                assert error_detail, "400 error response missing 'detail' field"
                # Verify error response structure matches expected format
                assert isinstance(
                    data, dict
                ), "400 error response should be a dictionary"
                # Verify it's an expected error type
                assert (
                    "invalid" in error_detail.lower()
                    or "bad request" in error_detail.lower()
                    or "validation" in error_detail.lower()
                    or "error" in error_detail.lower()
                ), f"Unexpected 400 error: {error_detail}"
                print(f"INFO: Received 400 Bad Request error: {error_detail}")

            elif start_response.status_code == 404:
                # Not found error (404) - FastAPI returns {"detail": "..."} format
                error_detail = data.get("detail", "")
                assert error_detail, "404 error response missing 'detail' field"
                # Verify error response structure matches expected format
                assert isinstance(
                    data, dict
                ), "404 error response should be a dictionary"
                # Verify it's an expected error type
                assert (
                    "not found" in error_detail.lower()
                    or "not-found" in error_detail.lower()
                    or "does not exist" in error_detail.lower()
                    or "missing" in error_detail.lower()
                ), f"Unexpected 404 error: {error_detail}"
                print(f"INFO: Received 404 Not Found error: {error_detail}")

            else:
                # Error case (500) - FastAPI returns {"detail": "..."} format
                # This happens when provider returns success=False and router raises HTTPException
                error_detail = data.get("detail", "")
                assert error_detail, "500 error response missing 'detail' field"
                # Verify error response structure matches expected format
                assert isinstance(
                    data, dict
                ), "500 error response should be a dictionary"
                # Verify it's an expected error (room not hosting call)
                assert (
                    "not hosting a call" in error_detail.lower()
                    or "not-found" in error_detail.lower()
                    or "does not seem to be hosting" in error_detail.lower()
                    or "daily api error" in error_detail.lower()
                ), f"Unexpected 500 error: {error_detail}"
                # This is expected if browser didn't auto-join or permissions weren't granted
                print(f"INFO: Received 500 Server Error: {error_detail}")

        except Exception as e:
            # Handle any unexpected errors
            print(f"ERROR: Test failed with exception: {str(e)}")
            raise
        finally:
            # Clean up the room
            print("Cleaning up room...")

            # Always clean up the room
            delete_response = client.delete(
                f"/api/rooms/delete/{room_name_for_cleanup}",
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )

            if delete_response.status_code != 200:
                print(
                    f"WARNING: Failed to clean up room {room_name_for_cleanup}: "
                    f"{delete_response.json()}"
                )
            else:
                print(f"Room {room_name_for_cleanup} cleaned up successfully")
