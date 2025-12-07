#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test the new simplified bot API.

This script demonstrates how to use the new simplified bot API:
1. Creates a Daily room (or uses an existing one)
2. Starts a bot via POST /api/bot/join
3. Polls GET /api/bot/{bot_id}/status to check progress
4. Shows results when complete

**Simple Explanation:**
This script tests the new simplified bot system that:
- Joins existing Daily rooms (no complex workflows)
- Automatically transcribes and processes results
- Returns results via the status endpoint

Run with: python flow/demos/test_bot_api.py

Required environment variables:
- DAILY_API_KEY: Daily.co API key for room creation
- OPENAI_API_KEY: OpenAI API key for bot LLM and insights
- DEEPGRAM_API_KEY: Deepgram API key for speech-to-text
- SUPABASE_URL: Supabase project URL
- SUPABASE_SERVICE_ROLE_KEY: Supabase service role key
- ENCRYPTION_KEY: Encryption key for database (at least 32 characters)

Optional:
- API_BASE_URL: Base URL for API (defaults to http://localhost:8001, which is flow/main.py)
- TEST_ROOM_URL: Use existing room URL instead of creating one

Note: The API is now in flow/main.py, so make sure to run:
  cd flow && python main.py
"""

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

import httpx

# Add project root to path so we can import flow modules
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)  # flow/
project_root = os.path.dirname(flow_dir)  # project root (pailkit/)
sys.path.insert(0, project_root)


async def create_daily_room(api_key: str) -> dict:
    """
    Create a Daily.co room for testing.

    Simple Explanation: This creates a new Daily room that we can use for testing.
    Returns the room URL that we'll pass to the bot API.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Create a room with a unique name
    room_name = f"test-bot-{int(time.time())}"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.daily.co/v1/rooms",
            headers=headers,
            json={"name": room_name, "privacy": "private"},
        )
        response.raise_for_status()
        room_data = response.json()

        return {
            "room_name": room_data["name"],
            "room_url": room_data["url"],
        }


async def start_bot(api_base_url: str, room_url: str, token: str = None) -> dict:
    """
    Start a bot via the new simplified API.

    Simple Explanation: This calls the POST /api/bot/join endpoint to start a bot
    in the specified room. It returns a bot_id that we can use to check status.
    """
    bot_config = {
        "bot_prompt": """You are a friendly AI assistant conducting a casual interview.
Ask the participant about:
- Their background and experience
- What they're working on
- Their interests and goals

Keep it conversational and natural. Ask one question at a time and wait for responses.
After 3-4 questions, wrap up politely.""",
        "name": "InterviewBot",
        "video_mode": "static",
        "static_image": "robot01.png",
    }

    payload = {
        "room_url": room_url,
        "token": token,
        "bot_config": bot_config,
        "process_insights": True,  # Enable automatic insight extraction
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{api_base_url}/api/bot/join",
            json=payload,
            headers={"Authorization": "Bearer test-key"},  # You may need to adjust this
        )
        response.raise_for_status()
        return response.json()


async def get_bot_status(api_base_url: str, bot_id: str) -> dict:
    """
    Get bot status via the status endpoint.

    Simple Explanation: This calls GET /api/bot/{bot_id}/status to check
    the current status and results of the bot session.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{api_base_url}/api/bot/{bot_id}/status",
            headers={"Authorization": "Bearer test-key"},  # You may need to adjust this
        )
        response.raise_for_status()
        return response.json()


async def main():
    """Test the new simplified bot API."""
    load_dotenv()

    # Get configuration
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8001")
    daily_api_key = os.getenv("DAILY_API_KEY")
    test_room_url = os.getenv("TEST_ROOM_URL")  # Optional: use existing room

    if not daily_api_key and not test_room_url:
        print(
            "❌ Missing required: DAILY_API_KEY (or set TEST_ROOM_URL to use existing room)"
        )
        sys.exit(1)

    print(f"\n{'='*80}")
    print("🧪 Testing Simplified Bot API")
    print(f"{'='*80}\n")

    # Step 1: Create or use existing room
    if test_room_url:
        print(f"📋 Using existing room: {test_room_url}")
        room_url = test_room_url
        room_name = test_room_url.split("/")[-1]
    else:
        print("📋 Creating Daily room...")
        room_info = await create_daily_room(daily_api_key)
        room_url = room_info["room_url"]
        room_name = room_info["room_name"]
        print(f"   ✅ Room created: {room_name}")
        print(f"   Room URL: {room_url}\n")

    # Step 2: Start bot
    print(f"{'='*80}")
    print("🤖 Starting bot...")
    print(f"{'='*80}\n")

    try:
        bot_response = await start_bot(api_base_url, room_url)
        bot_id = bot_response["bot_id"]
        print("✅ Bot started successfully!")
        print(f"   Bot ID: {bot_id}")
        print(f"   Status: {bot_response['status']}")
        print(f"   Room URL: {bot_response['room_url']}\n")
    except httpx.HTTPStatusError as e:
        print(f"❌ Failed to start bot: {e}")
        if e.response.status_code == 401:
            print("   💡 Check your API authentication (Authorization header)")
        elif e.response.status_code == 500:
            print("   💡 Check server logs for errors")
            print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        sys.exit(1)

    # Step 3: Poll for status
    print(f"{'='*80}")
    print("⏳ Polling bot status...")
    print(f"{'='*80}\n")
    print("   Join the room and have a conversation with the bot!")
    print(f"   Room URL: {room_url}\n")
    print("   Press Ctrl+C to stop polling (bot will continue running)\n")

    try:
        last_status = None
        poll_count = 0

        while True:
            await asyncio.sleep(2)  # Poll every 2 seconds
            poll_count += 1

            try:
                status = await get_bot_status(api_base_url, bot_id)
                current_status = status["status"]

                # Only print if status changed
                if current_status != last_status:
                    print(f"   [{poll_count}] Status: {current_status}")
                    if status.get("started_at"):
                        print(f"        Started: {status['started_at']}")
                    if status.get("completed_at"):
                        print(f"        Completed: {status['completed_at']}")
                    last_status = current_status

                # Check if bot finished
                if current_status == "completed":
                    print(f"\n{'='*80}")
                    print("✅ Bot completed!")
                    print(f"{'='*80}\n")

                    # Show results
                    if status.get("transcript"):
                        transcript_preview = status["transcript"][:200]
                        print(f"📝 Transcript (preview): {transcript_preview}...")
                        print(
                            f"   Full length: {len(status['transcript'])} characters\n"
                        )

                    if status.get("qa_pairs"):
                        print(f"❓ Q&A Pairs: {len(status['qa_pairs'])} pairs found\n")
                        for i, qa in enumerate(
                            status["qa_pairs"][:3], 1
                        ):  # Show first 3
                            print(f"   {i}. Q: {qa.get('question', 'N/A')[:60]}...")
                            print(f"      A: {qa.get('answer', 'N/A')[:60]}...\n")

                    if status.get("insights"):
                        insights = status["insights"]
                        print("🧠 Insights:")
                        if insights.get("overall_score") is not None:
                            print(f"   Overall Score: {insights['overall_score']}/10")
                        if insights.get("strengths"):
                            print(f"   Strengths: {len(insights['strengths'])} items")
                        if insights.get("weaknesses"):
                            print(f"   Weaknesses: {len(insights['weaknesses'])} items")
                        print()

                    break
                elif current_status == "failed":
                    print(f"\n{'='*80}")
                    print("❌ Bot failed!")
                    print(f"{'='*80}\n")
                    if status.get("error"):
                        print(f"   Error: {status['error']}\n")
                    break

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    print("   ⚠️ Bot session not found (may have been cleaned up)")
                    break
                else:
                    print(f"   ⚠️ Error checking status: {e}")
            except Exception as e:
                print(f"   ⚠️ Error checking status: {e}")

    except KeyboardInterrupt:
        print("\n\n⏸️  Polling stopped (bot may still be running)")
        print("   You can check status later with:")
        print(f"   GET {api_base_url}/api/bot/{bot_id}/status\n")

    print(f"{'='*80}")
    print("🎉 Test complete!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
