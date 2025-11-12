#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test script to create a real Daily.co room using the CreateRoomStep.

This script tests the actual room creation with real API calls to Daily.co.
Make sure you have your Daily.co API key set in the DAILY_API_KEY environment variable
or in the .env file.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from flow.steps.interview.create_room import CreateRoomStep  # noqa: E402

# Load environment variables from flow/.env
load_dotenv()  # Load flow/.env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_create_room():
    """Test creating a real Daily.co room."""
    # Get API key from environment or prompt
    api_key = os.getenv("DAILY_API_KEY")

    if not api_key:
        print("❌ DAILY_API_KEY not found in environment variables.")
        print("Please set it in your .env file or export it:")
        print("  export DAILY_API_KEY=your-daily-api-key")
        print("\nOr add it to flow/.env:")
        print("  DAILY_API_KEY=your-daily-api-key")
        return False

    print(f"✅ Found Daily API key: {api_key[:10]}...")
    print("\n🧪 Testing room creation...\n")

    # Create the step
    step = CreateRoomStep()

    # Prepare test state
    state = {
        "session_id": "test-session-real",
        "provider_keys": {
            "room_provider_key": api_key,
            "room_provider": "daily",
        },
        "interview_config": {
            "live_captions": False,
            "branding": {
                "logo_url": "https://example.com/logo.png",
                "colors": {
                    "background": "rgba(18, 26, 36, 1)",
                    "text": "rgba(255, 255, 255, 1)",
                    "border": "rgba(43, 63, 86, 1)",
                },
            },
        },
    }

    try:
        # Execute the step
        result = await step.execute(state)

        # Check results
        if result.get("error"):
            print(f"❌ Error creating room: {result['error']}")
            return False

        if result.get("processing_status") == "room_created":
            print("✅ Room created successfully!\n")
            print(f"📹 Room URL: {result.get('room_url')}")
            print(f"🆔 Room ID: {result.get('room_id')}")
            print(f"📝 Room Name: {result.get('room_name')}")
            print(f"🎨 Branding: {result.get('branding', 'None')}")
            print(f"\n🌐 You can join the room at: {result.get('room_url')}")
            return True
        else:
            print(f"❌ Unexpected status: {result.get('processing_status')}")
            print(f"   Error: {result.get('error', 'None')}")
            return False

    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


async def test_create_room_minimal():
    """Test creating a room with minimal configuration."""
    api_key = os.getenv("DAILY_API_KEY")

    if not api_key:
        print("❌ DAILY_API_KEY not found")
        return False

    print("\n🧪 Testing minimal room creation (no branding)...\n")

    step = CreateRoomStep()
    state = {
        "session_id": "test-session-minimal",
        "provider_keys": {
            "room_provider_key": api_key,
            "room_provider": "daily",
        },
        "interview_config": {},
    }

    try:
        result = await step.execute(state)

        if result.get("error"):
            print(f"❌ Error: {result['error']}")
            return False

        if result.get("processing_status") == "room_created":
            print("✅ Minimal room created successfully!")
            print(f"📹 Room URL: {result.get('room_url')}")
            return True
        else:
            print(f"❌ Status: {result.get('processing_status')}")
            return False

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Daily.co Room Creation Test")
    print("=" * 60)
    print()

    # Run tests
    success1 = asyncio.run(test_create_room())
    print()
    success2 = asyncio.run(test_create_room_minimal())

    print()
    print("=" * 60)
    if success1 and success2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)
