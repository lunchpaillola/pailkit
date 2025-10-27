"""
Tests for the rooms router with profile-based API.

Note: Most tests are mocked for speed and reliability.
Set RUN_INTEGRATION_TESTS=true environment variable to run real API tests.
"""

import os
from typing import Any
from unittest.mock import AsyncMock, patch

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

    @patch("routers.rooms.daily_provider")
    def test_create_room_with_conversation_profile(self, mock_provider: Any) -> None:
        """Test creating a room with conversation profile."""
        # Mock the provider response
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-conversation-123",
            "provider": "daily",
            "room_url": "https://example.daily.co/test-conversation-123",
            "profile": "conversation",
            "message": "Room created successfully"
        })

        # Test data with profile
        room_data = {
            "profile": "conversation"
        }

        # Make request
        response = client.post("/api/rooms/create", json=room_data)

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["room_id"] == "test-conversation-123"
        assert data["profile"] == "conversation"
        assert "room_url" in data

    @patch("routers.rooms.daily_provider")
    def test_create_room_with_broadcast_profile(self, mock_provider: Any) -> None:
        """Test creating a room with broadcast profile."""
        # Mock the provider response
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-broadcast-123",
            "provider": "daily",
            "room_url": "https://example.daily.co/test-broadcast-123",
            "profile": "broadcast",
            "message": "Room created successfully"
        })

        # Test data with broadcast profile
        room_data = {
            "profile": "broadcast"
        }

        # Make request
        response = client.post("/api/rooms/create", json=room_data)

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["profile"] == "broadcast"

    @patch("routers.rooms.daily_provider")
    def test_create_room_with_overrides(self, mock_provider: Any) -> None:
        """Test creating a room with profile and overrides."""
        # Mock the provider response
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-override-123",
            "provider": "daily",
            "room_url": "https://example.daily.co/test-override-123",
            "profile": "conversation",
            "message": "Room created successfully"
        })

        # Test data with profile and overrides
        room_data = {
            "profile": "conversation",
            "overrides": {
                "capabilities": {
                    "chat": False
                }
            }
        }

        # Make request
        response = client.post("/api/rooms/create", json=room_data)

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_create_room_unsupported_provider(self) -> None:
        """Test room creation with unsupported provider."""
        room_data = {
            "profile": "conversation",
            "provider": "unsupported"
        }

        response = client.post("/api/rooms/create", json=room_data)

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported provider" in data["detail"]

    @patch("routers.rooms.daily_provider")
    def test_create_room_provider_failure(self, mock_provider: Any) -> None:
        """Test room creation when provider fails."""
        # Mock provider failure
        mock_provider.create_room = AsyncMock(return_value={
            "success": False,
            "message": "Daily API error: Invalid API key"
        })

        room_data = {
            "profile": "conversation"
        }

        response = client.post("/api/rooms/create", json=room_data)

        assert response.status_code == 500
        data = response.json()
        assert "Invalid API key" in data["detail"]

    @pytest.mark.skipif(not RUN_INTEGRATION_TESTS, reason="Integration tests disabled")
    def test_create_room_real_api_conversation(self) -> None:
        """Integration test: Create a real conversation room using Daily.co API."""
        room_data = {
            "profile": "conversation"
        }

        response = client.post("/api/rooms/create", json=room_data)

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
        delete_response = client.delete(f"/api/rooms/delete/{room_name}")
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

        response = client.post("/api/rooms/create", json=room_data)

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
        delete_response = client.delete(f"/api/rooms/delete/{room_name}")
        if delete_response.status_code == 200:
            print(f"🧹 Room {room_name} cleaned up successfully")
        else:
            print(f"⚠️  Failed to clean up room {room_name}: {delete_response.json()}")
