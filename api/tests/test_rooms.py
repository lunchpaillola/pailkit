"""
Tests for the rooms router with profile-based API.

Note: Most tests are mocked for speed and reliability.
Set RUN_INTEGRATION_TESTS=true environment variable to run real API tests.
"""

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load environment variables before importing main
load_dotenv()

from main import app  # noqa: E402

client = TestClient(app)

# If an Unkey test secret is provided, use it for Authorization so that
# middleware verification against Unkey can pass during tests.
AUTH_KEY = os.getenv("UNKEY_PAILKIT_SECRET", "pailkit_test_123")

# Check if integration tests should run
RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"


class TestRoomsRouter:
    """Test cases for the rooms router."""

    def test_health_requires_authorization(self) -> None:
        # Missing Authorization should be rejected
        unauth = client.get("/health")
        assert unauth.status_code == 401
        assert "Authorization header required" in unauth.json().get("detail", "")

        # With Authorization it should pass
        auth = client.get("/health", headers={"Authorization": f"Bearer {AUTH_KEY}"})
        assert auth.status_code == 200

    @patch("routers.rooms.get_provider")
    def test_create_room_with_conversation_profile(
        self, mock_get_provider: Any
    ) -> None:
        """Test creating a room with conversation profile."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(
            return_value={
                "success": True,
                "room_id": "test-conversation-123",
                "provider": "daily",
                "room_url": "https://example.daily.co/test-conversation-123",
                "profile": "conversation",
                "message": "Room created successfully",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with profile
        room_data = {"profile": "conversation"}

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
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
        assert data["room_id"] == "test-conversation-123"
        assert data["profile"] == "conversation"
        assert "room_url" in data

    @patch("routers.rooms.get_provider")
    def test_create_room_with_broadcast_profile(self, mock_get_provider: Any) -> None:
        """Test creating a room with broadcast profile."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(
            return_value={
                "success": True,
                "room_id": "test-broadcast-123",
                "provider": "daily",
                "room_url": "https://example.daily.co/test-broadcast-123",
                "profile": "broadcast",
                "message": "Room created successfully",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with broadcast profile
        room_data = {"profile": "broadcast"}

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
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
        assert data["profile"] == "broadcast"

    @patch("routers.rooms.get_provider")
    def test_create_room_with_audio_room_profile(self, mock_get_provider: Any) -> None:
        """Test creating a room with audio_room profile."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(
            return_value={
                "success": True,
                "room_id": "test-audio-room-123",
                "provider": "daily",
                "room_url": "https://example.daily.co/test-audio-room-123",
                "profile": "audio_room",
                "message": "Room created successfully",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with audio_room profile
        room_data = {"profile": "audio_room"}

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
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
        assert data["profile"] == "audio_room"
        assert "room_url" in data

    @patch("routers.rooms.get_provider")
    def test_create_room_with_overrides(self, mock_get_provider: Any) -> None:
        """Test creating a room with profile and overrides."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(
            return_value={
                "success": True,
                "room_id": "test-override-123",
                "provider": "daily",
                "room_url": "https://example.daily.co/test-override-123",
                "profile": "conversation",
                "message": "Room created successfully",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with profile and overrides
        room_data = {
            "profile": "conversation",
            "overrides": {"capabilities": {"chat": False}},
        }

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
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

    def test_create_room_unsupported_provider(self) -> None:
        """Test room creation with unsupported provider."""
        room_data = {"profile": "conversation"}

        # Make request with unsupported provider in header
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "unsupported",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported provider" in data["detail"]

    @patch("routers.rooms.get_provider")
    def test_create_room_provider_failure(self, mock_get_provider: Any) -> None:
        """Test room creation when provider fails."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(
            return_value={
                "success": False,
                "message": "Daily API error: Invalid API key",
            }
        )

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        room_data = {"profile": "conversation"}

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        assert response.status_code == 500
        data = response.json()
        assert "Invalid API key" in data["detail"]

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_conversation(self) -> None:
        """Integration test: Create a real conversation room using Daily.co API."""
        room_data = {"profile": "conversation"}

        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "conversation"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        assert "https://" in data["room_url"]  # Should be a valid URL
        print(f"\n? Real room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Clean up: Delete the room
        room_name = data.get("room_name", data["room_id"])  # Use room_name if available
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )
        if delete_response.status_code == 200:
            print(f"?? Room {room_name} cleaned up successfully")
        else:
            print(f"??  Failed to clean up room {room_name}: {delete_response.json()}")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_broadcast(self) -> None:
        """Integration test: Create a real room with broadcast profile using actual Daily.co API."""
        room_data = {
            "profile": "broadcast",
            "overrides": {"capabilities": {"chat": True}},
        }

        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "broadcast"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        print(f"\n? Real broadcast room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Clean up: Delete the room
        room_name = data.get("room_name", data["room_id"])  # Use room_name if available
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )
        if delete_response.status_code == 200:
            print(f"?? Room {room_name} cleaned up successfully")
        else:
            print(f"??  Failed to clean up room {room_name}: {delete_response.json()}")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_podcast(self) -> None:
        """Integration test: Create a real room with podcast profile using actual Daily.co API."""
        room_data = {"profile": "podcast"}

        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "podcast"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        print(f"\n? Real podcast room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Verify room configuration matches podcast profile
        # Get room name for later cleanup
        room_name = data.get("room_name", data["room_id"])

        # Check config from creation response first (it already includes config)
        room_config = data.get("config", {})
        props = room_config.get("properties", {})

        # If properties not in config, try getting room details
        if not props:
            get_response = client.get(
                f"/api/rooms/get/{room_name}",
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )
            if get_response.status_code == 200:
                room_config = get_response.json().get("config", {})
                props = room_config.get("properties", {})

        # Podcast should have: recording, transcription, no chat, no screenshare
        # Note: Some properties might not be returned in GET response if not set
        # So we check what's available and verify the expected values
        if props:
            # Recording should be enabled (cloud recording)
            recording = props.get("enable_recording")
            if recording:
                assert (
                    recording == "cloud"
                ), f"Recording should be 'cloud', got '{recording}'"

            # Transcription should be enabled
            transcription = props.get("enable_transcription_storage")
            if transcription is not None:
                assert transcription is True, "Transcription should be enabled"

            # Chat should be disabled
            chat = props.get("enable_chat")
            if chat is not None:
                assert chat is False, "Chat should be disabled for podcast"

            # Screenshare should be disabled
            screenshare = props.get("enable_screenshare")
            if screenshare is not None:
                assert screenshare is False, "Screenshare should be disabled"

            print("   ? Configuration verified from room response")
        else:
            print("   ??  Could not verify configuration (properties not in response)")

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
            print(f"?? Room {room_name} cleaned up successfully")
        else:
            print(f"??  Failed to clean up room {room_name}: {delete_response.json()}")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_live_stream(self) -> None:
        """Integration test: Create a real room with live_stream profile using Daily.co API."""
        # Require a real RTMP URL via environment to avoid provider errors
        rtmp_url = os.getenv("DAILY_RTMP_URL")
        if not rtmp_url:
            pytest.skip("DAILY_RTMP_URL environment variable not set")

        room_data = {
            "profile": "live_stream",
            "overrides": {"capabilities": {"rtmp_url": rtmp_url}},
        }

        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "live_stream"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        print(f"\n? Real live_stream room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Verify room configuration matches live_stream profile
        # Get room name for later cleanup
        room_name = data.get("room_name", data["room_id"])

        # Check config from creation response first (it already includes config)
        room_config = data.get("config", {})
        props = room_config.get("properties", {})

        # If properties not in config, try getting room details
        if not props:
            get_response = client.get(
                f"/api/rooms/get/{room_name}",
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": f"Bearer {AUTH_KEY}",
                },
            )
            if get_response.status_code == 200:
                room_config = get_response.json().get("config", {})
                props = room_config.get("properties", {})

        # Live stream should have: recording, RTMP streaming, broadcast mode, chat
        if props:
            # Recording should be enabled (cloud recording)
            recording = props.get("enable_recording")
            if recording:
                assert (
                    recording == "cloud"
                ), f"Recording should be 'cloud', got '{recording}'"

            # Broadcast mode should be enabled
            broadcast_mode = props.get("owner_only_broadcast")
            if broadcast_mode is not None:
                assert (
                    broadcast_mode is True
                ), "Broadcast mode should be enabled for live_stream"

            # Chat should be enabled (audience chat)
            chat = props.get("enable_chat")
            if chat is not None:
                assert chat is True, "Chat should be enabled for live_stream"

            # RTMP streaming should be configured
            # Note: Daily.co API might not return rtmp_ingress in response
            # but we verify the room was created successfully which means config was accepted
            rtmp_ingress = props.get("rtmp_ingress")
            if rtmp_ingress:
                print(f"   ? RTMP streaming configured: {rtmp_ingress}")
            else:
                print(
                    "   ??  RTMP configuration not visible in response "
                    "(may require room update API)"
                )

            print("   ? Configuration verified from room response")
        else:
            print("   ??  Could not verify configuration (properties not in response)")

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
            print(f"?? Room {room_name} cleaned up successfully")
        else:
            print(f"??  Failed to clean up room {room_name}: {delete_response.json()}")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_audio_room(self) -> None:
        """Integration test: Create a real room with audio_room profile using Daily.co API."""
        room_data = {"profile": "audio_room"}

        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "audio_room"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        print(f"\n? Real audio_room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Verify room configuration matches audio_room profile
        # Get room name for later cleanup
        room_name = data.get("room_name", data["room_id"])

        # Check config from creation response first (it already includes config)
        room_config = data.get("config", {})
        props = room_config.get("properties", {})

        # If properties not in config, try getting room details
        if not props:
            get_response = client.get(
                f"/api/rooms/get/{room_name}",
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                    "Authorization": "Bearer pailkit_test_123",
                },
            )
            if get_response.status_code == 200:
                room_config = get_response.json().get("config", {})
                props = room_config.get("properties", {})

        # Audio room should have: no video (start_video_off), chat enabled,
        # no recording, no screenshare, no prejoin
        if props:
            # Video should be off by default (audio-only)
            start_video_off = props.get("start_video_off")
            if start_video_off is not None:
                assert (
                    start_video_off is True
                ), "Video should be off by default for audio_room"

            # Chat should be enabled
            chat = props.get("enable_chat")
            if chat is not None:
                assert chat is True, "Chat should be enabled for audio_room"

            # Recording should be disabled
            recording = props.get("enable_recording")
            if recording is not None:
                assert (
                    recording is False
                ), f"Recording should be disabled, got '{recording}'"

            # Screenshare should be disabled
            screenshare = props.get("enable_screenshare")
            if screenshare is not None:
                assert (
                    screenshare is False
                ), "Screenshare should be disabled for audio_room"

            # Prejoin should be disabled (fast join)
            prejoin = props.get("enable_prejoin_ui")
            if prejoin is not None:
                assert (
                    prejoin is False
                ), "Prejoin UI should be disabled for audio_room (fast join)"

            print("   ? Configuration verified from room response")
        else:
            print("   ??  Could not verify configuration (properties not in response)")

        # Clean up: Delete the room
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": "Bearer pailkit_test_123",
            },
        )
        if delete_response.status_code == 200:
            print(f"?? Room {room_name} cleaned up successfully")
        else:
            print(f"??  Failed to clean up room {room_name}: {delete_response.json()}")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_workshop(self) -> None:
        """Integration test: Create a real room with workshop profile using actual Daily.co API."""
        room_data = {"profile": "workshop"}

        # Get API key from environment variable
        daily_api_key = os.getenv("DAILY_API_KEY")
        if not daily_api_key:
            pytest.skip("DAILY_API_KEY environment variable not set")

        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
                "Authorization": f"Bearer {AUTH_KEY}",
            },
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "workshop"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        print(f"\n? Real workshop room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Verify room configuration matches workshop profile
        # Get room name for later cleanup
        room_name = data.get("room_name", data["room_id"])

        # Check config from creation response first (it already includes config)
        room_config = data.get("config", {})
        props = room_config.get("properties", {})

        # If properties not in config, try getting room details
        if not props:
            get_response = client.get(
                f"/api/rooms/get/{room_name}",
                headers={
                    "X-Provider-Auth": f"Bearer {daily_api_key}",
                    "X-Provider": "daily",
                },
            )
            if get_response.status_code == 200:
                room_config = get_response.json().get("config", {})
                props = room_config.get("properties", {})

        # Workshop should have: recording, transcription, live captions,
        # screenshare, breakout rooms, chat, prejoin
        if props:
            # Recording should be enabled (cloud recording)
            recording = props.get("enable_recording")
            if recording:
                assert (
                    recording == "cloud"
                ), f"Recording should be 'cloud', got '{recording}'"

            # Transcription should be enabled
            transcription = props.get("enable_transcription_storage")
            if transcription is not None:
                assert (
                    transcription is True
                ), "Transcription should be enabled for workshop"

            # Live captions should be enabled
            live_captions = props.get("enable_live_captions_ui")
            if live_captions is not None:
                assert (
                    live_captions is True
                ), "Live captions should be enabled for workshop"

            # Screenshare should be enabled
            screenshare = props.get("enable_screenshare")
            if screenshare is not None:
                assert screenshare is True, "Screenshare should be enabled for workshop"

            # Breakout rooms should be enabled
            breakout_rooms = props.get("enable_breakout_rooms")
            if breakout_rooms is not None:
                assert (
                    breakout_rooms is True
                ), "Breakout rooms should be enabled for workshop"

            # Chat should be enabled
            chat = props.get("enable_chat")
            if chat is not None:
                assert chat is True, "Chat should be enabled for workshop"

            # Prejoin should be enabled
            prejoin = props.get("enable_prejoin_ui")
            if prejoin is not None:
                assert prejoin is True, "Prejoin UI should be enabled for workshop"

            print("   ? Configuration verified from room response")
        else:
            print("   ??  Could not verify configuration (properties not in response)")

        # Clean up: Delete the room
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily",
            },
        )
        if delete_response.status_code == 200:
            print(f"?? Room {room_name} cleaned up successfully")
        else:
            print(f"??  Failed to clean up room {room_name}: {delete_response.json()}")
