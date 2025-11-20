#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Create a room with bot enabled for manual testing.

This script creates a real room, enables the bot, and waits so you can join.

Run with: python flow/scripts/create_room_with_bot.py

Note: This requires valid API keys in your .env file:
- DAILY_API_KEY
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path so we can import flow modules
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)  # flow/
project_root = os.path.dirname(flow_dir)  # project root (pailkit/)
sys.path.insert(0, project_root)

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow  # noqa: E402


async def main():
    """Create room with bot and wait for user to join."""
    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")

    if not daily_api_key:
        print("❌ Missing required API key: DAILY_API_KEY")
        sys.exit(1)

    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": False,
            "autoTranscribe": True,
            "bot": {
                "enabled": True,
                "video_mode": "animated",  # Use animated sprite mode
                "animation_frames_per_sprite": 10,  # Slower animation - each frame shows 5 times
            },
        },
        "provider_keys": {
            "room_provider_key": daily_api_key,
        },
    }

    # Set the base URL for the hosted meeting page
    os.environ["MEET_BASE_URL"] = os.getenv("MEET_BASE_URL", "http://localhost:8001")

    print(f"\n{'='*80}")
    print("🚀 Creating room with bot enabled...")
    print(f"{'='*80}\n")

    result = await workflow.execute_async(context)

    # Get room info from result
    room_name = result.get("room_name")
    room_url = result.get("room_url")
    hosted_url = result.get("hosted_url")
    bot_joined = result.get("bot_joined", False)

    print(f"\n{'='*80}")
    print("✅ ROOM CREATED SUCCESSFULLY!")
    print(f"{'='*80}\n")

    if room_name:
        print("📋 Room Details:")
        print(f"   Room Name: {room_name}")
        print(f"   Room URL: {room_url}\n")

        print(f"{'='*80}")
        print("🔗 JOIN THE MEETING - Use this localhost URL:")
        if hosted_url:
            print(f"   {hosted_url}")
        else:
            # Fallback to room_url if hosted_url not available
            print(f"   {room_url}")
        print(f"{'='*80}\n")

        if hosted_url and hosted_url.startswith("http://localhost"):
            print("💡 NOTE: Make sure the server is running:")
            print("   cd flow && python main.py")
            print("   Then open the URL above in your browser\n")
        elif not hosted_url:
            print("💡 NOTE: To use the localhost hosted page, start the server:")
            print("   cd flow && python main.py")
            print(
                f"   Then visit: http://localhost:8001/meet/{room_name}?autoRecord=true&autoTranscribe=true&bot=true\n"
            )

        print(f"{'='*80}")
        print("🤖 Bot Status:")
        print(f"{'='*80}")
        if bot_joined:
            print("   ✅ Bot joined successfully!")
            print("   The bot should be in the room waiting for you!")
        else:
            print("   ⚠️ Bot did not join")
            print("   Check bot configuration")
        print(f"{'='*80}\n")

        print("💡 TIP: Open the meeting link in your browser to join as a participant")
        print("   The bot should already be in the room\n")

        print(f"{'='*80}")
        print("⏳ Waiting for you to join the room...")
        print("   Press Ctrl+C to exit when done")
        print(f"{'='*80}\n")

        # Keep the script running so the user can join
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print(f"\n\n👋 Exiting... Room will remain available at: {room_url}\n")
    else:
        print("\n❌ Room creation failed!")
        print(f"Error: {result.get('error')}")
        print(f"{'='*80}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
