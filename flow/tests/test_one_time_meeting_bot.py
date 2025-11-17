# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Tests for one_time_meeting workflow with bot functionality.

These tests verify that:
1. The workflow includes bot=true parameter when bot is enabled
2. The JoinBotStep is executed correctly
3. URLs include bot parameter for Pipecat client initialization
"""

import pytest
from unittest.mock import AsyncMock, patch
import os

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow


@pytest.mark.asyncio
async def test_url_with_bot_enabled():
    """Test that URLs include bot=true parameter when bot is enabled."""
    workflow = OneTimeMeetingWorkflow()

    # Mock both CreateRoomStep and JoinBotStep
    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class, patch(
        "flow.workflows.one_time_meeting.JoinBotStep"
    ) as mock_join_bot_class:

        # Mock CreateRoomStep
        mock_create_step = AsyncMock()
        mock_create_step.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_create_step

        # Mock JoinBotStep
        mock_join_step = AsyncMock()
        mock_join_step.execute = AsyncMock(
            return_value={
                "bot_joined": True,
                "bot_config": {"enabled": True},
                "processing_status": "bot_joined",
                "error": None,
            }
        )
        mock_join_bot_class.return_value = mock_join_step

        # Create a new workflow instance to use the mocked steps
        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "autoRecord": True,
                "autoTranscribe": True,
                "bot": {"enabled": True},
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

        # Verify bot parameter is included
        assert "bot=true" in hosted_url
        assert "autoRecord=true" in hosted_url
        assert "autoTranscribe=true" in hosted_url

        # Verify both steps were called
        mock_create_step.execute.assert_called_once()
        mock_join_step.execute.assert_called_once()


@pytest.mark.asyncio
async def test_url_with_bot_disabled():
    """Test that URLs don't include bot parameter when bot is disabled."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class, patch(
        "flow.workflows.one_time_meeting.JoinBotStep"
    ) as mock_join_bot_class:

        # Mock CreateRoomStep
        mock_create_step = AsyncMock()
        mock_create_step.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_create_step

        # Mock JoinBotStep
        mock_join_step = AsyncMock()
        mock_join_step.execute = AsyncMock(
            return_value={
                "bot_joined": False,
                "processing_status": "bot_skipped",
                "error": None,
            }
        )
        mock_join_bot_class.return_value = mock_join_step

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "autoRecord": True,
                "autoTranscribe": True,
                "bot": {"enabled": False},
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

        # Verify bot parameter is NOT included
        assert "bot=true" not in hosted_url
        assert "autoRecord=true" in hosted_url
        assert "autoTranscribe=true" in hosted_url


@pytest.mark.asyncio
async def test_create_real_room_with_bot():
    """Create a real room with bot enabled for testing."""
    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": True,
            "autoTranscribe": True,
            "bot": {"enabled": True},
        },
        "provider_keys": {
            "room_provider_key": os.getenv("DAILY_API_KEY"),
            "room_provider": "daily",
        },
    }

    os.environ["MEET_BASE_URL"] = "http://localhost:8001"

    result = await workflow.execute_async(context)

    assert result["success"] is True, f"Room creation failed: {result.get('error')}"
    assert "hosted_url" in result, "No hosted_url in result"

    hosted_url = result["hosted_url"]
    room_name = result.get("room_name")
    has_token = "token=" in hosted_url

    print(f"\n{'='*80}")
    print("✅ Room with bot created successfully!")
    print(f"Room Name: {room_name}")
    print(f"Room URL: {result.get('room_url')}")
    print(f"Token included: {has_token}")
    print("\n🌐 Test URL with Bot (open in browser):")
    print(f"{hosted_url}")
    print(f"{'='*80}\n")

    assert "autoRecord=true" in hosted_url
    assert "autoTranscribe=true" in hosted_url
    assert "bot=true" in hosted_url

    return hosted_url
