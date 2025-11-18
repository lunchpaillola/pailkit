#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Create a room with bot enabled for manual testing.

This script creates a real room, starts the bot, and keeps it running
so you can test it in your browser. The bot will stay active until you stop it.

Run with: python flow/scripts/create_room_with_bot_for_testing.py

Note: This requires valid API keys in your .env file:
- DAILY_API_KEY
- OPENAI_API_KEY
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
    """Create room with bot and keep it running for testing."""
    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not daily_api_key:
        print("❌ Missing DAILY_API_KEY in environment variables")
        sys.exit(1)

    if not openai_api_key:
        print("❌ Missing OPENAI_API_KEY in environment variables")
        sys.exit(1)

    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": True,
            "autoTranscribe": True,
            "bot": {"enabled": True},
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
        print("🔗 JOIN THE MEETING - Use this link:")
        print(f"   {hosted_url or room_url}")
        print(f"{'='*80}\n")

        if hosted_url and hosted_url.startswith("http://localhost"):
            print("💡 NOTE: Make sure the server is running:")
            print("   cd flow && python main.py")
            print(f"   Then visit: {hosted_url}\n")

        print(f"{'='*80}")
        print("🤖 Bot Status:")
        print(f"{'='*80}")
        if bot_joined:
            print("   ✅ Bot is running and waiting for participants!")
            print("   The bot will greet you when you join the room.")
        else:
            print("   ⚠️ Bot may not have started - check logs above")
        print(f"{'='*80}\n")

        print(f"{'='*80}")
        print("⏳ Bot is running - join the room to test it!")
        print("   Press Ctrl+C to exit (bot will continue running)")
        print(f"{'='*80}\n")

        # Keep the script running so the bot stays alive
        # The bot runs in a background task, so we just need to keep this process alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 Exiting... Bot will continue running in the background")
            print(f"   Room remains available at: {room_url}\n")
    else:
        print("\n❌ Room creation failed!")
        print(f"Error: {result.get('error')}")
        print(f"{'='*80}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
