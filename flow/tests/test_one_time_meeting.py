# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test for one_time_meeting workflow that creates a real room and returns the URL.

Run this test to get a working room URL for testing transcription and recording:
    pytest flow/tests/test_one_time_meeting.py::test_create_room_and_get_url -v -s
"""

import os
import pytest
from dotenv import load_dotenv

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow

load_dotenv()


@pytest.mark.asyncio
async def test_create_room_and_get_url():
    """Create a real room and return the URL for testing."""
    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": True,
            "autoTranscribe": True,
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
    print("✅ Room created successfully!")
    print(f"Room Name: {room_name}")
    print(f"Room URL: {result.get('room_url')}")
    print(f"Token included: {has_token}")
    print("\n🌐 Test URL (open in browser):")
    print(f"{hosted_url}")
    print(f"{'='*80}\n")

    assert "autoRecord=true" in hosted_url
    assert "autoTranscribe=true" in hosted_url

    return hosted_url
