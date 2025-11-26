# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Tests for one_time_meeting workflow URL parameter generation.

These tests verify that:
1. The workflow generates URLs with autoRecord and autoTranscribe parameters
2. Other URL parameters (theme, accentColor, logoText) are included
3. Parameters default correctly
"""

import pytest
from unittest.mock import AsyncMock, patch
import os

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow


@pytest.mark.asyncio
async def test_url_with_auto_start_parameters():
    """Test that URLs include autoRecord and autoTranscribe parameters."""
    workflow = OneTimeMeetingWorkflow()

    # Mock the CreateRoomStep to return a room
    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class:
        mock_step = AsyncMock()
        mock_step.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_step

        # Create a new workflow instance to use the mocked step
        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "autoRecord": True,
                "autoTranscribe": True,
            },
            "provider_keys": {
                "room_provider_key": "test-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        assert "hosted_url" in result
        assert "autoRecord=true" in result["hosted_url"]
        assert "autoTranscribe=true" in result["hosted_url"]


@pytest.mark.asyncio
async def test_url_with_optional_parameters():
    """Test that URLs include optional parameters like theme, accentColor, logoText."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class:
        mock_step = AsyncMock()
        mock_step.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_step

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "autoRecord": True,
                "autoTranscribe": True,
                "theme": "dark",
                "accentColor": "#ff0000",
                "logoText": "MyCompany",
            },
            "provider_keys": {
                "room_provider_key": "test-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        assert "hosted_url" in result
        hosted_url = result["hosted_url"]
        assert "autoRecord=true" in hosted_url
        assert "autoTranscribe=true" in hosted_url
        assert "theme=dark" in hosted_url
        assert (
            "accentColor=%23ff0000" in hosted_url or "accentColor=#ff0000" in hosted_url
        )
        assert "logoText=MyCompany" in hosted_url


@pytest.mark.asyncio
async def test_url_defaults_to_auto_start():
    """Test that autoRecord and autoTranscribe default to True."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class:
        mock_step = AsyncMock()
        mock_step.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_step

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {},  # No autoRecord/autoTranscribe specified
            "provider_keys": {
                "room_provider_key": "test-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        assert "hosted_url" in result
        # Should default to True
        assert "autoRecord=true" in result["hosted_url"]
        assert "autoTranscribe=true" in result["hosted_url"]


@pytest.mark.asyncio
async def test_url_with_auto_start_disabled():
    """Test that URLs don't include parameters when auto-start is disabled."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class:
        mock_step = AsyncMock()
        mock_step.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_step

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "autoRecord": False,
                "autoTranscribe": False,
            },
            "provider_keys": {
                "room_provider_key": "test-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        assert "hosted_url" in result
        # Should not include autoRecord or autoTranscribe when False
        assert "autoRecord" not in result["hosted_url"]
        assert "autoTranscribe" not in result["hosted_url"]
