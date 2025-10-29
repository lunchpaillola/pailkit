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

# Check if integration tests should run
RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"


class TestRoomsRouter:
    """Test cases for the rooms router."""

    @patch("routers.rooms.get_provider")
    def test_create_room_with_conversation_profile(self, mock_get_provider: Any) -> None:
        """Test creating a room with conversation profile."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-conversation-123",
            "provider": "daily",
            "room_url": "https://example.daily.co/test-conversation-123",
            "profile": "conversation",
            "message": "Room created successfully"
        })

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with profile
        room_data = {
            "profile": "conversation"
        }

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily"
            }
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
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-broadcast-123",
            "provider": "daily",
            "room_url": "https://example.daily.co/test-broadcast-123",
            "profile": "broadcast",
            "message": "Room created successfully"
        })

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with broadcast profile
        room_data = {
            "profile": "broadcast"
        }

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily"
            }
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["profile"] == "broadcast"

    @patch("routers.rooms.get_provider")
    def test_create_room_with_overrides(self, mock_get_provider: Any) -> None:
        """Test creating a room with profile and overrides."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-override-123",
            "provider": "daily",
            "room_url": "https://example.daily.co/test-override-123",
            "profile": "conversation",
            "message": "Room created successfully"
        })

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        # Test data with profile and overrides
        room_data = {
            "profile": "conversation",
            "overrides": {
                "capabilities": {
                    "chat": False
                }
            }
        }

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily"
            }
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_create_room_unsupported_provider(self) -> None:
        """Test room creation with unsupported provider."""
        room_data = {
            "profile": "conversation"
        }

        # Make request with unsupported provider in header
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "unsupported"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported provider" in data["detail"]

    @patch("routers.rooms.get_provider")
    def test_create_room_provider_failure(self, mock_get_provider: Any) -> None:
        """Test room creation when provider fails."""
        # Create a mock provider instance
        mock_provider = MagicMock()
        mock_provider.create_room = AsyncMock(return_value={
            "success": False,
            "message": "Daily API error: Invalid API key"
        })

        # Make get_provider return our mock
        mock_get_provider.return_value = mock_provider

        room_data = {
            "profile": "conversation"
        }

        # Make request with required headers
        response = client.post(
            "/api/rooms/create",
            json=room_data,
            headers={
                "X-Provider-Auth": "Bearer test-api-key-123",
                "X-Provider": "daily"
            }
        )

        assert response.status_code == 500
        data = response.json()
        assert "Invalid API key" in data["detail"]

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_conversation(self) -> None:
        """Integration test: Create a real conversation room using Daily.co API."""
        room_data = {
            "profile": "conversation"
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
                "X-Provider": "daily"
            }
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
        print(f"\n✅ Real room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Clean up: Delete the room
        room_name = data.get("room_name", data["room_id"])  # Use room_name if available
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily"
            }
        )
        if delete_response.status_code == 200:
            print(f"🧹 Room {room_name} cleaned up successfully")
        else:
            print(f"⚠️  Failed to clean up room {room_name}: {delete_response.json()}")

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_broadcast(self) -> None:
        """Integration test: Create a real room with broadcast profile using actual Daily.co API."""
        room_data = {
            "profile": "broadcast",
            "overrides": {
                "capabilities": {
                    "chat": True
                }
            }
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
                "X-Provider": "daily"
            }
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "daily"
        assert data["profile"] == "broadcast"
        assert "room_id" in data and data["room_id"]
        assert "room_url" in data and data["room_url"]
        print(f"\n✅ Real broadcast room created! Room ID: {data['room_id']}")
        print(f"   Room URL: {data['room_url']}")

        # Clean up: Delete the room
        room_name = data.get("room_name", data["room_id"])  # Use room_name if available
        delete_response = client.delete(
            f"/api/rooms/delete/{room_name}",
            headers={
                "X-Provider-Auth": f"Bearer {daily_api_key}",
                "X-Provider": "daily"
            }
        )
        if delete_response.status_code == 200:
            print(f"🧹 Room {room_name} cleaned up successfully")
        else:
            print(f"⚠️  Failed to clean up room {room_name}: {delete_response.json()}")
