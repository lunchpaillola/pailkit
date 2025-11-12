#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test script for one-time meeting creation.

This script creates a Daily.co room and returns both the room URL and hosted URL.
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

# Get base URL for hosted meetings
MEET_BASE_URL = os.getenv("MEET_BASE_URL", "http://localhost:8001")


async def test_create_one_time_meeting():
    """Create a one-time meeting room and return the URLs."""
    # Get API key from environment
    api_key = os.getenv("DAILY_API_KEY")

    if not api_key:
        print("❌ DAILY_API_KEY not found in environment variables.")
        print("Please set it in your .env file or export it:")
        print("  export DAILY_API_KEY=your-daily-api-key")
        return None

    print(f"✅ Found Daily API key: {api_key[:10]}...")
    print("\n🚀 Creating one-time meeting room...\n")

    # Prepare Daily.co API request
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": (
            f"Bearer {api_key}" if not api_key.startswith("Bearer ") else api_key
        ),
    }

    # Room configuration
    room_config = {
        "properties": {
            "enable_prejoin_ui": True,
            "enable_chat": False,
            "enable_screenshare": True,
        },
        "privacy": "public",
    }

    try:
        # Create the room
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.daily.co/v1/rooms",
                headers=headers,
                json=room_config,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            room_url = result.get("url", "")
            room_name = room_url.split("/")[-1] if room_url else ""
            room_id = result.get("id")

            # Generate hosted URL
            hosted_url = f"{MEET_BASE_URL}/meet/{room_name}?room_url={room_url}"

            # Display results
            print("=" * 70)
            print("✅ Room created successfully!")
            print("=" * 70)
            print()
            print("📹 Direct Room URL (Daily.co):")
            print(f"   {room_url}")
            print()
            print("🌐 Hosted Meeting Page:")
            print(f"   {hosted_url}")
            print()
            print(f"📝 Room Name: {room_name}")
            print(f"🆔 Room ID: {room_id}")
            print()
            print("=" * 70)
            print("💡 Share the hosted URL with participants to join!")
            print("=" * 70)

            return {
                "room_url": room_url,
                "hosted_url": hosted_url,
                "room_name": room_name,
                "room_id": room_id,
            }

    except httpx.HTTPStatusError as e:
        error_detail = "Unknown error"
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", str(e))
        except Exception:
            error_detail = str(e)

        print(f"❌ Daily API error: {error_detail}")
        print(f"   Status code: {e.response.status_code}")
        return None

    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("=" * 70)
    print("One-Time Meeting Room Creation Test")
    print("=" * 70)
    print()

    result = asyncio.run(test_create_one_time_meeting())

    if result:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed")
