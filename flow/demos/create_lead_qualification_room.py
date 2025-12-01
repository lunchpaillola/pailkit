#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Create a lead qualification room with bot for pre-qualifying leads.

This script creates a room with an AI bot that conducts a short qualification call,
asks 5 key questions, and generates a clean lead summary.

**Demo Features:**
- Pre-configured bot that asks qualification questions
- Structured lead summary with fit score
- Email/webhook output with JSON format

Run with: python flow/demos/create_lead_qualification_room.py

Required environment variables in your .env file:
- DAILY_API_KEY: Daily.co API key for room creation
- OPENAI_API_KEY: OpenAI API key for AI-powered transcript analysis
- DEEPGRAM_API_KEY: Deepgram API key for speech-to-text transcription
- RESEND_API_KEY: Resend API key for sending email results (optional)
- RESEND_EMAIL_DOMAIN: Verified email domain in Resend (optional, required if using email)
- ENCRYPTION_KEY: Encryption key for database (required, at least 32 characters)

Optional environment variables:
- TEST_EMAIL: Email to send results to (defaults to test@example.com)
- TEST_NAME: Name of the lead (defaults to Unknown, will be extracted from call if provided)
- TEST_WEBHOOK_SITE: Webhook URL for testing (defaults to webhook.site URL)
- MEET_BASE_URL: Base URL for hosted meeting page (defaults to http://localhost:8001)
"""

import asyncio
import os
import sys
from typing import Any
from dotenv import load_dotenv

# Add project root to path so we can import flow modules
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)  # flow/
project_root = os.path.dirname(flow_dir)  # project root (pailkit/)
sys.path.insert(0, project_root)

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow  # noqa: E402


async def create_lead_qualification_room(
    participant_name: str | None = None,
    participant_email: str | None = None,
) -> dict[str, Any]:
    """
    Create a lead qualification room with bot.

    This is the core function that can be called from scripts or API endpoints.
    Returns the workflow result with room information.
    """
    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")
    test_email = participant_email or os.getenv("TEST_EMAIL", "test@example.com")
    test_name = participant_name or os.getenv("TEST_NAME", "Unknown")
    test_webhook_site = os.getenv(
        "TEST_WEBHOOK_SITE", "https://webhook.site/38c8fcd9-00e6-48d2-a169-32856a7e76fe"
    )

    if not daily_api_key:
        raise ValueError("Missing required API key: DAILY_API_KEY")

    workflow = OneTimeMeetingWorkflow()

    # ============================================================================
    # CONFIGURATION: Lead Qualification Bot Prompts
    # ============================================================================

    # Bot Prompt: Defines what the bot should do and say during qualification
    bot_prompt = """You are conducting a lead qualification call. Your goal is to ask 5 key questions to understand if this lead is a good fit.

Welcome the person warmly and say: "Hi! I'm going to ask you a few quick questions to see how we can help. This will only take a couple of minutes."

Then ask these 5 questions, ONE AT A TIME, waiting for a complete answer before moving to the next:

1. "What problem are you trying to solve?"
   - Wait for their answer
   - If unclear, ask one follow-up: "Can you tell me more about that?"

2. "What have you tried so far to solve this?"
   - Wait for their answer
   - If unclear, ask: "Have you tried any solutions or workarounds?"

3. "How soon do you need this solved?"
   - Wait for their answer
   - If unclear, ask: "Is this urgent, or are you planning ahead?"

4. "What's your budget range for solving this?"
   - Wait for their answer
   - If they're hesitant, say: "Just a rough range is fine, like under $1k, $1k-$10k, etc."

5. "Who is involved in the decision-making process?"
   - Wait for their answer
   - If unclear, ask: "Is this your decision, or do others need to approve?"

After getting all 5 answers, say: "Perfect! I have everything I need. I'll send you a summary via email shortly. Thanks for your time!"

Guidelines:
- Keep it friendly and conversational
- Don't rush - let them finish answering
- Only ask follow-ups if an answer is truly unclear
- If they ask questions, answer briefly and redirect to the qualification questions
- Keep the call under 5 minutes
- End politely after collecting all information"""

    # Analysis Prompt: Defines how to extract structured data from the conversation
    analysis_prompt = """Analyze this lead qualification call transcript and extract the following information:

Extract these fields from the conversation:
1. **person_name**: The lead's name (if mentioned, otherwise "Unknown")
2. **problem**: What problem they're trying to solve (from question 1)
3. **current_workaround**: What they've tried so far (from question 2)
4. **timeline**: How soon they need this solved (from question 3)
5. **budget**: Their budget range (from question 4)
6. **decision_maker**: Who is involved in decision-making (from question 5)

Then calculate a **quick_fit_score** (1-10) based on:
- Clear problem statement (2 points)
- Urgent timeline (under 1 month = 2 points, 1-3 months = 1 point)
- Budget range indicated (2 points)
- Decision maker identified (2 points)
- Specific workaround/attempts mentioned (2 points)

Provide a JSON response with:
- person_name (string)
- problem (string)
- current_workaround (string)
- timeline (string)
- budget (string)
- decision_maker (string)
- quick_fit_score (number 1-10)

Transcript: {transcript}"""

    # Summary Format Prompt: Defines how to format the final output
    summary_format_prompt = """Create a lead qualification summary in this exact JSON format.

Extract the following fields from the insights in the Context Data:
- person_name (from insights.person_name)
- problem (from insights.problem)
- current_workaround (from insights.current_workaround)
- timeline (from insights.timeline)
- budget (from insights.budget)
- decision_maker (from insights.decision_maker)
- quick_fit_score (from insights.quick_fit_score, should be a number 1-10)

Output this exact JSON structure:

{{
  "call_name": "Lead Qualification Call",
  "lead": {{
    "name": "<extract from insights.person_name, use 'Unknown' if not available>",
    "problem": "<extract from insights.problem, use 'Not specified' if not available>",
    "current_workaround": "<extract from insights.current_workaround, use 'Not specified' if not available>",
    "timeline": "<extract from insights.timeline, use 'Not specified' if not available>",
    "budget": "<extract from insights.budget, use 'Not specified' if not available>",
    "decision_maker": "<extract from insights.decision_maker, use 'Not specified' if not available>",
    "quick_fit_score": <extract from insights.quick_fit_score, must be a number>
  }},
  "recommendation": "<calculate based on quick_fit_score: if >= 7 use 'Book a demo at https://cal.com/lunchpaillabs/intro', if >= 4 use 'Schedule a discovery call to learn more', if < 4 use 'Send follow-up email with resources'>"
}}

IMPORTANT:
- Output ONLY valid JSON, no additional text before or after
- Use the insights data from the Context Data provided
- Calculate recommendation based on quick_fit_score value
- Use "Unknown" or "Not specified" for missing fields
- Ensure quick_fit_score is a number, not a string"""

    # Lead information (name can be extracted from call, but use TEST_NAME as fallback)
    participant_info = {
        "name": test_name,  # From .env file (TEST_NAME), may be updated from call
        "email": test_email,  # From .env file (TEST_EMAIL)
        "role": "Lead",  # Generic role for qualification calls
    }

    context = {
        "meeting_config": {
            "autoRecord": False,
            # When bot is enabled, TranscriptProcessor handles transcription automatically
            "autoTranscribe": False,
            "webhook_callback_url": test_webhook_site,  # Test webhook endpoint from .env
            "email_results_to": test_email,  # From .env file (TEST_EMAIL)
            "interview_type": "Lead Qualification Call",  # This will appear in the summary
            "difficulty_level": "beginner",  # Not applicable but required field
            # Bot configuration with qualification prompts
            "bot": {
                "enabled": True,
                "bot_prompt": bot_prompt,  # This controls what the bot says/does
                "video_mode": "animated",  # Use animated sprite mode
                "animation_frames_per_sprite": 1,  # Show each frame once (faster animation)
            },
            # Analysis prompt - controls how the conversation is analyzed
            "analysis_prompt": analysis_prompt,
            # Summary format prompt - controls how results are formatted
            "summary_format_prompt": summary_format_prompt,
            # Also include participant info in meeting_config for easier access
            "participant_name": participant_info.get("name", "Unknown"),
            "role": participant_info.get("role", "Lead"),
            "position": participant_info.get(
                "role", "Lead"
            ),  # Use role as position for email subject
        },
        "participant_info": participant_info,
        "session_id": f"lead-qual-{int(asyncio.get_event_loop().time())}",  # Unique session ID
        "provider_keys": {
            "room_provider_key": daily_api_key,
        },
    }

    # Set the base URL for the hosted meeting page
    os.environ["MEET_BASE_URL"] = os.getenv("MEET_BASE_URL", "http://localhost:8001")

    # Execute the workflow
    result = await workflow.execute_async(context)
    return result


async def main():
    """Create lead qualification room with bot and wait for user to join."""
    print(f"\n{'='*80}")
    print("🚀 Creating lead qualification room with bot...")
    print(f"{'='*80}\n")

    result = await create_lead_qualification_room()

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
        print("🔗 JOIN THE QUALIFICATION CALL - Use this URL:")
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
            print(f"   Then visit: http://localhost:8001/meet/{room_name}?bot=true\n")

        print(f"{'='*80}")
        print("🤖 Bot Status:")
        print(f"{'='*80}")
        if bot_joined:
            print("   ✅ Bot joined successfully!")
            print("   The bot will ask 5 qualification questions:")
            print("   1. What problem are you trying to solve?")
            print("   2. What have you tried so far?")
            print("   3. How soon do you need this solved?")
            print("   4. What's your budget range?")
            print("   5. Who is involved in the decision?")
            print("\n   After the call, a lead summary will be sent via email/webhook.")
        else:
            print("   ⚠️ Bot did not join")
            print("   Check bot configuration")
        print(f"{'='*80}\n")

        print("💡 TIP: Open the meeting link in your browser to join as the lead")
        print("   The bot will conduct the qualification call\n")

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
