#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test the new simplified bot API.

This script demonstrates how to use the new simplified bot API:
1. Uses an existing Daily room (via TEST_ROOM_URL)
2. Starts a bot via POST /api/bot/join
3. Generates a hosted meeting link automatically
4. Polls GET /api/bot/{bot_id}/status to check progress
5. Shows results when complete

**Simple Explanation:**
This script tests the new simplified bot system that:
- Joins existing Daily rooms (no complex workflows)
- Automatically transcribes and processes results
- Returns results via the status endpoint
- Generates a hosted meeting link you can open in your browser

Run with: python flow/demos/test_bot_api.py

Required environment variables:
- TEST_ROOM_URL: Daily.co room URL to use (e.g., https://domain.daily.co/room-name)
- UNKEY_PAILKIT_SECRET: PailKit API key (Unkey) for authenticating API requests
- OPENAI_API_KEY: OpenAI API key for bot LLM and insights
- DEEPGRAM_API_KEY: Deepgram API key for speech-to-text
- SUPABASE_URL: Supabase project URL
- SUPABASE_SERVICE_ROLE_KEY: Supabase service role key
- ENCRYPTION_KEY: Encryption key for database (at least 32 characters)

Optional:
- API_BASE_URL: Base URL for API (defaults to http://localhost:8001, which is flow/main.py)
- TEST_ROOM_TOKEN: Daily.co room token (if room requires authentication)
- TEST_EMAIL: Email to send results to (defaults to test@example.com)
- TEST_NAME: Candidate name (defaults to Alex Johnson)
- TEST_WEBHOOK_SITE: Webhook URL for testing
- INTERVIEW_TYPE: Interview type (defaults to "Technical Interview")

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


async def start_bot(
    api_base_url: str,
    room_url: str,
    token: str = None,
    bot_prompt: str = None,
    candidate_name: str = None,
    candidate_email: str = None,
    interview_type: str = None,
    analysis_prompt: str = None,
    webhook_url: str = None,
) -> dict:
    """
    Start a bot via the new simplified API.

    Simple Explanation: This calls the POST /api/bot/join endpoint to start a bot
    in the specified room. It returns a bot_id that we can use to check status.
    """
    # Use provided bot_prompt or default
    if not bot_prompt:
        bot_prompt = """You are conducting a technical interview for a Senior Software Engineer position.
Your role is to assess the candidate's technical skills, problem-solving abilities, and communication.

Ask questions about:
- Python programming and best practices
- Backend development and API design
- System design and architecture
- Problem-solving approaches
- Database design

Guidelines:
- Ask one question at a time
- Wait for the candidate to finish answering before moving on
- Provide brief, encouraging feedback when appropriate
- Keep the tone professional but warm
- If the candidate asks for clarification, provide it
- After 5-7 questions, wrap up the interview politely"""

    bot_config = {
        "bot_prompt": bot_prompt,
        "name": "InterviewBot",
        "video_mode": "animated",
        "static_image": "robot01.png",
    }

    payload = {
        "room_url": room_url,
        "token": token,
        "bot_config": bot_config,
        "process_insights": True,  # Enable automatic insight extraction
    }

    # Get API key from environment (Unkey PailKit API key)
    api_key = os.getenv("UNKEY_PAILKIT_SECRET", "test-key")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{api_base_url}/api/bot/join",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        bot_response = response.json()

        # Save session data to database (for email, webhook, interview context)
        # Simple Explanation: We save candidate info, email, and analysis prompts
        # to the database so they can be used when processing the transcript
        if candidate_name or candidate_email or interview_type:
            room_name = room_url.split("/")[-1]
            try:
                from flow.db import get_session_data, save_session_data

                session_data = get_session_data(room_name) or {}
                if candidate_name:
                    session_data["candidate_name"] = candidate_name
                if candidate_email:
                    session_data["email_results_to"] = candidate_email
                if interview_type:
                    session_data["interview_type"] = interview_type
                if analysis_prompt:
                    session_data["analysis_prompt"] = analysis_prompt
                if webhook_url:
                    session_data["webhook_callback_url"] = webhook_url

                # Also set position and interviewer_context for better summaries
                if interview_type:
                    session_data["position"] = "Senior Software Engineer"  # Default
                    session_data["interviewer_context"] = (
                        "Technical interview focusing on software engineering skills"
                    )

                save_session_data(room_name, session_data)
                print(
                    "   ✅ Saved session data (candidate info, email, prompts) to database"
                )
            except Exception as e:
                print(f"   ⚠️ Warning: Could not save session data: {e}")

        return bot_response


async def get_bot_status(api_base_url: str, bot_id: str) -> dict:
    """
    Get bot status via the status endpoint.

    Simple Explanation: This calls GET /api/bot/{bot_id}/status to check
    the current status and results of the bot session.
    """
    # Get API key from environment (Unkey PailKit API key)
    api_key = os.getenv("UNKEY_PAILKIT_SECRET", "test-key")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{api_base_url}/api/bot/{bot_id}/status",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        return response.json()


async def main():
    """Test the new simplified bot API."""
    load_dotenv()

    # Get configuration
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8001")
    test_room_url = os.getenv("TEST_ROOM_URL")  # Required: existing room URL
    test_room_token = os.getenv("TEST_ROOM_TOKEN")  # Optional: room token

    # Get optional configuration for interview context (like create_room_with_bot.py)
    test_email = os.getenv("TEST_EMAIL", "test@example.com")
    test_name = os.getenv("TEST_NAME", "Alex Johnson")
    test_webhook_site = os.getenv(
        "TEST_WEBHOOK_SITE", "https://webhook.site/38c8fcd9-00e6-48d2-a169-32856a7e76fe"
    )
    interview_type = os.getenv("INTERVIEW_TYPE", "Technical Interview")

    if not test_room_url:
        print("❌ Missing required: TEST_ROOM_URL")
        print(
            "   Set TEST_ROOM_URL to the Daily.co room URL (e.g., https://domain.daily.co/room-name)"
        )
        sys.exit(1)

    print(f"\n{'='*80}")
    print("🧪 Testing Simplified Bot API")
    print(f"{'='*80}\n")

    # Extract room name from room URL
    # Simple Explanation: We get the room name from the end of the room URL
    # e.g., "https://domain.daily.co/DEV-123" -> "DEV-123"
    room_url = test_room_url
    room_name = test_room_url.rstrip("/").split("/")[-1]
    print("📋 Using existing room:")
    print(f"   Room Name: {room_name}")
    print(f"   Room URL: {room_url}\n")

    # Show candidate info (like create_room_with_bot.py)
    print("👤 Candidate Information:")
    print(f"   Name: {test_name}")
    print(f"   Email: {test_email}")
    print(f"   Interview Type: {interview_type}\n")

    # Step 2: Start bot
    print(f"{'='*80}")
    print("🤖 Starting bot...")
    print(f"{'='*80}\n")

    # Create analysis prompt (like create_room_with_bot.py)
    analysis_prompt = """Analyze this technical interview transcript and provide a comprehensive assessment.

Focus on evaluating:
- Technical Skills: Depth of knowledge, relevant experience, ability to explain concepts
- Problem Solving: Approach to problems, logical thinking, ability to break down complex issues
- Communication: Clarity of explanations, articulation, listening skills
- Code Quality: Understanding of best practices, code organization, attention to detail
- System Design: Ability to design scalable systems, consider trade-offs, discuss architecture

Transcript: {transcript}

Provide a JSON response with:
- overall_score (0-10)
- competency_scores for each area above (0-10 each)
- strengths (2-4 specific points)
- weaknesses (2-4 areas for improvement)
- question_assessments (score and notes for each Q&A pair)

Be constructive and specific. Focus on what was actually said in the transcript."""

    # Create bot prompt (like create_room_with_bot.py)
    bot_prompt = """You are conducting a technical interview for a Senior Software Engineer position.
Your role is to assess the candidate's technical skills, problem-solving abilities, and communication.

Ask questions about:
- Python programming and best practices
- Backend development and API design
- System design and architecture
- Problem-solving approaches
- Database design

Guidelines:
- Ask one question at a time
- Wait for the candidate to finish answering before moving on
- Provide brief, encouraging feedback when appropriate
- Keep the tone professional but warm
- If the candidate asks for clarification, provide it
- After 5-7 questions, wrap up the interview politely"""

    try:
        bot_response = await start_bot(
            api_base_url,
            room_url,
            token=test_room_token,  # Pass token if provided
            bot_prompt=bot_prompt,
            candidate_name=test_name,
            candidate_email=test_email,
            interview_type=interview_type,
            analysis_prompt=analysis_prompt,
            webhook_url=test_webhook_site,
        )
        bot_id = bot_response["bot_id"]
        print("✅ Bot started successfully!")
        print(f"   Bot ID: {bot_id}")
        print(f"   Status: {bot_response['status']}")
        print(f"   Room URL: {bot_response['room_url']}\n")

        # Generate hosted link automatically
        # Simple Explanation: We create the hosted meeting URL that you can open in your browser
        # It includes the room_url and token as parameters so the meeting page can join the room
        hosted_url_parts = [f"{api_base_url}/meet/{room_name}"]
        hosted_url_parts.append(f"room_url={room_url}")
        if test_room_token:
            hosted_url_parts.append(f"token={test_room_token}")
        hosted_url = "?".join(hosted_url_parts)

        print(f"{'='*80}")
        print("🔗 JOIN THE MEETING - Use this URL:")
        print(f"   {hosted_url}")
        print(f"{'='*80}\n")

        print("💡 NOTE: Make sure the server is running:")
        print("   cd flow && python main.py")
        print("   Then open the URL above in your browser\n")
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
    print("   Use the hosted URL above to join the meeting")
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
