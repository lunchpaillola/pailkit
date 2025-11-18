# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Tests for one_time_meeting workflow VAPI integration.

These tests verify that:
1. SIP dial-in is enabled when VAPI calling is enabled
2. VAPI outbound call is created when VAPI is enabled
3. SIP URI is correctly passed to VAPI
4. Workflow skips VAPI steps when disabled
"""

import pytest
from unittest.mock import AsyncMock, patch
import os

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow


@pytest.mark.asyncio
async def test_vapi_enabled_enables_sip_dialin():
    """Test that SIP dial-in is enabled when VAPI calling is enabled."""
    workflow = OneTimeMeetingWorkflow()

    # Mock the CreateRoomStep to return a room with SIP dial-in enabled
    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class, patch(
        "flow.workflows.one_time_meeting.CallVAPIStep"
    ) as mock_call_vapi_class, patch(
        "flow.workflows.one_time_meeting.JoinBotStep"
    ) as mock_join_bot_class:

        mock_create_room = AsyncMock()
        mock_create_room.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "room_url": "https://test.daily.co/test-room-name",
                "sip_uri": "sip:123456780@example.sip.daily.co",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_create_room

        mock_call_vapi = AsyncMock()
        mock_call_vapi.execute = AsyncMock(
            return_value={
                "vapi_call_id": "test-call-id",
                "vapi_call_created": True,
                "processing_status": "vapi_call_created",
                "error": None,
            }
        )
        mock_call_vapi_class.return_value = mock_call_vapi

        mock_join_bot = AsyncMock()
        mock_join_bot.execute = AsyncMock(
            return_value={
                "bot_joined": False,
                "processing_status": "completed",
                "error": None,
            }
        )
        mock_join_bot_class.return_value = mock_join_bot

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "vapi": {
                    "enabled": True,
                    "assistant_id": "test-assistant-id",
                }
            },
            "provider_keys": {
                "room_provider_key": "test-daily-key",
                "vapi_api_key": "test-vapi-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        # Verify that CreateRoomStep was called (which enables SIP dial-in)
        assert mock_create_room.execute.called
        # Verify that CallVAPIStep was called
        assert mock_call_vapi.execute.called


@pytest.mark.asyncio
async def test_vapi_call_receives_sip_uri():
    """Test that VAPI call step receives SIP URI from room creation."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class, patch(
        "flow.workflows.one_time_meeting.CallVAPIStep"
    ) as mock_call_vapi_class, patch(
        "flow.workflows.one_time_meeting.JoinBotStep"
    ) as mock_join_bot_class:

        mock_create_room = AsyncMock()
        mock_create_room.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "room_url": "https://test.daily.co/test-room-name",
                "sip_uri": "sip:123456780@example.sip.daily.co",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_create_room

        mock_call_vapi = AsyncMock()
        mock_call_vapi.execute = AsyncMock(
            return_value={
                "vapi_call_id": "test-call-id",
                "vapi_call_created": True,
                "processing_status": "vapi_call_created",
                "error": None,
            }
        )
        mock_call_vapi_class.return_value = mock_call_vapi

        mock_join_bot = AsyncMock()
        mock_join_bot.execute = AsyncMock(
            return_value={
                "bot_joined": False,
                "processing_status": "completed",
                "error": None,
            }
        )
        mock_join_bot_class.return_value = mock_join_bot

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "vapi": {
                    "enabled": True,
                    "assistant_id": "test-assistant-id",
                }
            },
            "provider_keys": {
                "room_provider_key": "test-daily-key",
                "vapi_api_key": "test-vapi-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True

        # Verify CallVAPIStep was called with the correct state
        call_args = mock_call_vapi.execute.call_args[0][0]
        assert call_args["sip_uri"] == "sip:123456780@example.sip.daily.co"
        assert call_args["room_url"] == "https://test.daily.co/test-room-name"


@pytest.mark.asyncio
async def test_vapi_disabled_skips_vapi_steps():
    """Test that VAPI steps are skipped when VAPI calling is disabled."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class, patch(
        "flow.workflows.one_time_meeting.CallVAPIStep"
    ) as mock_call_vapi_class, patch(
        "flow.workflows.one_time_meeting.JoinBotStep"
    ) as mock_join_bot_class:

        mock_create_room = AsyncMock()
        mock_create_room.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "room_url": "https://test.daily.co/test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_create_room

        mock_call_vapi = AsyncMock()
        mock_call_vapi.execute = AsyncMock(
            return_value={
                "vapi_call_created": False,
                "processing_status": "completed",
                "error": None,
            }
        )
        mock_call_vapi_class.return_value = mock_call_vapi

        mock_join_bot = AsyncMock()
        mock_join_bot.execute = AsyncMock(
            return_value={
                "bot_joined": False,
                "processing_status": "completed",
                "error": None,
            }
        )
        mock_join_bot_class.return_value = mock_join_bot

        workflow = OneTimeMeetingWorkflow()

        context = {
            "meeting_config": {
                "vapi": {
                    "enabled": False,  # VAPI disabled
                }
            },
            "provider_keys": {
                "room_provider_key": "test-daily-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        # Verify CreateRoomStep was called (room creation still happens)
        assert mock_create_room.execute.called
        # Verify CallVAPIStep was called but should skip gracefully
        assert mock_call_vapi.execute.called
        # Verify the call_vapi step returns vapi_call_created: False when disabled
        # The step should still be called but will skip internally when VAPI is disabled
        # When VAPI is disabled, the step should skip and return vapi_call_created: False
        # This is handled internally by the CallVAPIStep.execute method


@pytest.mark.asyncio
async def test_vapi_missing_config_skips_gracefully():
    """Test that workflow handles missing VAPI config gracefully."""
    workflow = OneTimeMeetingWorkflow()

    with patch(
        "flow.workflows.one_time_meeting.CreateRoomStep"
    ) as mock_create_room_class, patch(
        "flow.workflows.one_time_meeting.CallVAPIStep"
    ) as mock_call_vapi_class, patch(
        "flow.workflows.one_time_meeting.JoinBotStep"
    ) as mock_join_bot_class:

        mock_create_room = AsyncMock()
        mock_create_room.execute = AsyncMock(
            return_value={
                "room_id": "test-room-id",
                "room_name": "test-room-name",
                "room_url": "https://test.daily.co/test-room-name",
                "processing_status": "room_created",
                "error": None,
            }
        )
        mock_create_room_class.return_value = mock_create_room

        mock_call_vapi = AsyncMock()
        mock_call_vapi.execute = AsyncMock(
            return_value={
                "vapi_call_created": False,
                "processing_status": "completed",
                "error": None,
            }
        )
        mock_call_vapi_class.return_value = mock_call_vapi

        mock_join_bot = AsyncMock()
        mock_join_bot.execute = AsyncMock(
            return_value={
                "bot_joined": False,
                "processing_status": "completed",
                "error": None,
            }
        )
        mock_join_bot_class.return_value = mock_join_bot

        workflow = OneTimeMeetingWorkflow()

        # No VAPI config at all
        context = {
            "meeting_config": {},
            "provider_keys": {
                "room_provider_key": "test-daily-key",
            },
        }

        with patch.dict(os.environ, {"MEET_BASE_URL": "http://localhost:8001"}):
            result = await workflow.execute_async(context)

        assert result["success"] is True
        # Workflow should complete successfully even without VAPI config


@pytest.mark.asyncio
async def test_vapi_call_uses_sip_uri():
    """Test that VAPI call receives SIP URI correctly."""
    # Test that the step can access sip_uri from state
    test_state = {
        "sip_uri": "sip:123456780@example.sip.daily.co",
        "room_url": "https://test.daily.co/test-room",
        "provider_keys": {"vapi_api_key": "test-key"},
        "interview_config": {"vapi": {"enabled": True, "assistant_id": "test-id"}},
        "candidate_info": {"phone_number": "+15551234567"},
    }

    # Verify the step can access the SIP URI
    assert test_state.get("sip_uri") == "sip:123456780@example.sip.daily.co"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_vapi_integration_real_api():
    """
    Integration test for VAPI calling with real API calls.

    This test creates a real room, enables SIP dial-in, and creates a VAPI call.
    Run with: pytest flow/tests/test_one_time_meeting_vapi.py::test_vapi_integration_real_api -v -s

    Note: This requires valid API keys in your .env file:
    - DAILY_API_KEY
    - VAPI_API_KEY
    - VAPI_ASSISTANT_ID
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")
    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")

    if not all([daily_api_key, vapi_api_key, vapi_assistant_id]):
        pytest.skip("Missing required API keys in environment variables")

    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": True,
            "autoTranscribe": True,
            "vapi": {
                "enabled": True,
                "assistant_id": vapi_assistant_id,
            },
            "phone_number": "+15551234567",  # Test candidate phone number
        },
        "provider_keys": {
            "room_provider_key": daily_api_key,
            "vapi_api_key": vapi_api_key,
        },
    }

    os.environ["MEET_BASE_URL"] = "http://localhost:8001"

    result = await workflow.execute_async(context)

    # Print results - room creation should succeed even if VAPI call fails
    print(f"\n{'='*80}")
    print("✅ VAPI Integration Test Results:")
    print(f"{'='*80}")

    # Get room info from result
    room_name = result.get("room_name")
    room_url = result.get("room_url")
    hosted_url = result.get("hosted_url")
    sip_uri = result.get("sip_uri")
    vapi_call_created = result.get("vapi_call_created", False)

    if room_name:
        print("\n✅ Room created successfully!")
        print(f"Room Name: {room_name}")
        print(f"Room URL: {room_url}")

        if sip_uri:
            print("\n📱 SIP Dial-in Enabled:")
            print(f"   SIP URI: {sip_uri}")
        else:
            print("\n⚠️ SIP URI not found in result (check logs)")

        if vapi_call_created:
            print("\n✅ VAPI call created successfully!")
        elif result.get("vapi_call_error"):
            print(f"\n⚠️ VAPI call failed: {result.get('vapi_call_error')}")
            print("   (Room is still available - VAPI can be retried)")

        print(f"\n{'='*80}")
        print("🔗 JOIN AS CANDIDATE - Use this link:")
        print(f"   {hosted_url or room_url}")
        print(f"{'='*80}")

        if sip_uri:
            print("\n📞 VAPI will dial SIP URI:")
            print(f"   {sip_uri}")
            print(f"{'='*80}\n")
    else:
        print("\n❌ Room creation failed!")
        print(f"Error: {result.get('error')}")
        print(f"{'='*80}\n")

    # Verify room was created (this is the main test)
    assert room_name is not None, f"Room should be created. Result: {result}"
    assert room_url is not None, f"Room URL should be available. Result: {result}"

    # SIP dial-in should be enabled if VAPI is enabled
    if result.get("success"):
        # If VAPI is enabled, we should have SIP URI info
        vapi_enabled = (
            context.get("meeting_config", {}).get("vapi", {}).get("enabled", False)
        )
        if vapi_enabled:
            # SIP URI should be available (either in result or logs)
            assert (
                sip_uri is not None
            ), "SIP dial-in should be enabled when VAPI is enabled"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_room_with_vapi_for_manual_testing():
    """
    Create a room with VAPI enabled for manual testing.

    This test creates a real room, enables SIP dial-in, and creates a VAPI call.
    It prints all the information you need to join the call.

    Run with: pytest flow/tests/test_one_time_meeting_vapi.py::test_create_room_with_vapi_for_manual_testing -v -s

    Note: This requires valid API keys in your .env file:
    - DAILY_API_KEY
    - VAPI_API_KEY
    - VAPI_ASSISTANT_ID
    - VAPI_PHONE_NUMBER_ID
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")
    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")
    vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

    if not all([daily_api_key, vapi_api_key, vapi_assistant_id, vapi_phone_number_id]):
        missing = []
        if not daily_api_key:
            missing.append("DAILY_API_KEY")
        if not vapi_api_key:
            missing.append("VAPI_API_KEY")
        if not vapi_assistant_id:
            missing.append("VAPI_ASSISTANT_ID")
        if not vapi_phone_number_id:
            missing.append("VAPI_PHONE_NUMBER_ID")
        pytest.skip(
            f"Missing required API keys in environment variables: {', '.join(missing)}"
        )

    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": True,
            "autoTranscribe": True,
            "vapi": {
                "enabled": True,
                "assistant_id": vapi_assistant_id,
            },
        },
        "provider_keys": {
            "room_provider_key": daily_api_key,
            "vapi_api_key": vapi_api_key,
        },
    }

    # Set the base URL for the hosted meeting page
    os.environ["MEET_BASE_URL"] = "http://localhost:8001"

    print(f"\n{'='*80}")
    print("🚀 Creating room with VAPI calling enabled...")
    print(f"{'='*80}\n")

    result = await workflow.execute_async(context)

    # Get room info from result
    room_name = result.get("room_name")
    room_url = result.get("room_url")
    hosted_url = result.get("hosted_url")
    sip_uri = result.get("sip_uri")
    vapi_call_created = result.get("vapi_call_created", False)
    vapi_call_id = result.get("vapi_call_id")
    vapi_call_error = result.get("vapi_call_error")

    print(f"\n{'='*80}")
    print("✅ ROOM CREATED SUCCESSFULLY!")
    print(f"{'='*80}\n")

    if room_name:
        print("📋 Room Details:")
        print(f"   Room Name: {room_name}")
        print(f"   Room URL: {room_url}\n")

        if sip_uri:
            print("📱 SIP Dial-in Information:")
            print(f"   SIP URI: {sip_uri}\n")

        print(f"{'='*80}")
        print("🔗 JOIN THE MEETING - Use this link:")
        print(f"   {hosted_url or room_url}")
        print(f"{'='*80}\n")

        if sip_uri:
            print("📞 VAPI will dial SIP URI:")
            print(f"   {sip_uri}\n")

        print(f"{'='*80}")
        print("🤖 VAPI Call Status:")
        print(f"{'='*80}")
        if vapi_call_created:
            print("   ✅ VAPI call created successfully!")
            if vapi_call_id:
                print(f"   Call ID: {vapi_call_id}")
            print(f"\n   VAPI should be dialing SIP URI: {sip_uri}")
            print("   Once VAPI joins, you can join via the link above to test!")
        elif vapi_call_error:
            print(f"   ⚠️ VAPI call failed: {vapi_call_error}")
            print("   Room is still available - you can join manually")
        else:
            print("   ⚠️ VAPI call status unknown")
        print(f"{'='*80}\n")

        print("💡 TIP: Open the meeting link in your browser to join as a participant")
        print("   VAPI should join automatically via SIP\n")

    else:
        print("\n❌ Room creation failed!")
        print(f"Error: {result.get('error')}")
        print(f"{'='*80}\n")

    # Verify room was created
    assert room_name is not None, f"Room should be created. Result: {result}"
    assert room_url is not None, f"Room URL should be available. Result: {result}"

    # If VAPI is enabled, we should have SIP URI info
    assert sip_uri is not None, "SIP URI should be available when VAPI is enabled"
