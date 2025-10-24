"""
Tests for the rooms router.
"""

import os
import pytest
from typing import Any
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from dotenv import load_dotenv

# Load environment variables before importing main
load_dotenv()

from main import app

client = TestClient(app)


class TestRoomsRouter:
    """Test cases for the rooms router."""

    @patch("routers.rooms.daily_provider")
    def test_create_room_success(self, mock_provider: Any) -> None:
        """Test successful room creation."""
        # Mock the provider response
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "test-room-123",
            "message": "Room created successfully",
            "room_url": "https://example.daily.co/test-room-123"
        })

        # Test data
        room_data = {
            "name": "Test Room",
            "room_type": "video",
            "privacy": "public",
            "provider": "daily"
        }

        # Make request
        response = client.post("/api/rooms/create", json=room_data)

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["room_id"] == "test-room-123"
        assert "room_url" in data

    @patch("routers.rooms.daily_provider")
    def test_create_room_with_defaults(self, mock_provider: Any) -> None:
        """Test room creation with default values."""
        # Mock the provider response
        mock_provider.create_room = AsyncMock(return_value={
            "success": True,
            "room_id": "default-room-123",
            "message": "Room created successfully"
        })

        # Test with minimal data
        room_data = {"name": "Minimal Room"}

        # Make request
        response = client.post("/api/rooms/create", json=room_data)

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_create_room_unsupported_provider(self) -> None:
        """Test room creation with unsupported provider."""
        room_data = {
            "name": "Test Room",
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
            "message": "Provider error"
        })

        room_data = {
            "name": "Test Room",
            "provider": "daily"
        }

        response = client.post("/api/rooms/create", json=room_data)

        assert response.status_code == 500
        data = response.json()
        assert "Provider error" in data["detail"]
