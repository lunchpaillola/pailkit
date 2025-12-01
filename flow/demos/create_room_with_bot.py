#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Create a room with bot enabled for manual testing and demos.

This script creates a real room, enables the bot, and waits so you can join.
Perfect for end-to-end testing and demos!

**Demo Features:**
- Pre-configured with realistic candidate information (Alex Johnson, Senior Software Engineer)
- AI-powered summary generation using custom prompts
- Proper participant name and role that will appear in summaries (not "Unknown")
- Clean summary format without "Assessment pending" messages

Run with: python flow/scripts/create_room_with_bot.py

Required environment variables in your .env file:
- DAILY_API_KEY: Daily.co API key for room creation
- OPENAI_API_KEY: OpenAI API key for AI-powered transcript analysis (optional but recommended)
- DEEPGRAM_API_KEY: Deepgram API key for speech-to-text transcription
- RESEND_API_KEY: Resend API key for sending email results (optional)
- RESEND_EMAIL_DOMAIN: Verified email domain in Resend (optional, required if using email)
- ENCRYPTION_KEY: Encryption key for database (required, at least 32 characters)

Optional environment variables:
- TEST_CANDIDATE_EMAIL: Email to send results to (defaults to test@example.com)
- TEST_WEBHOOK_SITE: Webhook URL for testing (defaults to webhook.site URL)
- MEET_BASE_URL: Base URL for hosted meeting page (defaults to http://localhost:8001)

Note: If OPENAI_API_KEY is not set, the analysis will use placeholder values.
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
    test_candidate_email = os.getenv("TEST_CANDIDATE_EMAIL", "test@example.com")
    test_webhook_site = os.getenv(
        "TEST_WEBHOOK_SITE", "https://webhook.site/38c8fcd9-00e6-48d2-a169-32856a7e76fe"
    )

    if not daily_api_key:
        print("❌ Missing required API key: DAILY_API_KEY")
        sys.exit(1)

    workflow = OneTimeMeetingWorkflow()

    # **Simple Explanation:** We're adding test session data here so that when
    # the room is created, it will have meaningful context data that gets passed
    # through to webhooks and can be used for testing the full interview flow.
    # We include interview_type, interviewer_context, and analysis parameters
    # so they appear in the summary and control how the AI analyzes the transcript.

    # ============================================================================
    # CONFIGURATION: Customize these prompts to control bot behavior and analysis
    # ============================================================================
    # These prompts are passed through to control:
    # 1. What the bot says/does (bot_prompt)
    # 2. How the conversation is analyzed (analysis_prompt)
    # 3. How results are formatted (summary_format_prompt)

    # Bot Prompt: Defines what the bot should do and say
    # **Simple Explanation:** This is the system message for the bot.
    # It tells the bot its role, what questions to ask, and how to behave.
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

    # Analysis Prompt: Defines how to analyze the conversation
    # **Simple Explanation:** This tells the AI how to evaluate the transcript.
    # Use {transcript} as a placeholder - it will be replaced with the actual conversation.
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

    # Summary Format Prompt: Defines how to format the results
    # **Simple Explanation:** This describes how you want the final summary/email to look.
    # The AI will use this prompt to generate a natural, less structured summary.
    summary_format_prompt = """Create a conversational summary of this interview.

Include:
- Participant information ({participant_name}, {role}, {conversation_type}, {conversation_date})
- Overall assessment and score
- Key competencies demonstrated (with scores if available)
- Main strengths and areas for improvement
- Summary of the Q&A discussion (only include scores if they are meaningful and non-zero)
- Brief reference to the full transcript

Write in a natural, professional tone. Focus on insights and observations rather than rigid formatting.
Do not include placeholder text like "Assessment pending" or show scores of 0/10 unless they are meaningful.
Make it readable and useful for understanding the candidate's performance."""

    # **Simple Explanation:** We're setting up the context that will be passed to the workflow.
    # This includes meeting_config (for room settings) and participant_info (for candidate data).
    # The participant_info will be used to populate the email subject and summary.
    participant_info = {
        "name": "Alex Johnson",  # This will appear in the summary
        "email": test_candidate_email,  # From .env file
        "role": "Senior Software Engineer",  # This will appear in the summary
        "position": "Senior Software Engineer",  # Alternative key name (for compatibility)
        "company": "TechCorp Inc.",  # Optional: company they're applying from
    }

    context = {
        "meeting_config": {
            "autoRecord": False,
            # When bot is enabled, TranscriptProcessor handles transcription automatically
            # So we don't need client-side autoTranscribe (which only transcribes the user)
            "autoTranscribe": False,
            "webhook_callback_url": test_webhook_site,  # Test webhook endpoint from .env
            "email_results_to": test_candidate_email,  # From .env file
            "interview_type": "Technical Interview",  # This will appear in the summary
            "difficulty_level": "intermediate",
            # Bot configuration with prompt-driven behavior
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
            "participant_name": participant_info["name"],
            "role": participant_info["role"],
        },
        # **Simple Explanation:** This is the candidate/participant information that will
        # appear in the summary. Make sure to include name and role so they show up
        # properly instead of "Unknown".
        "participant_info": participant_info,  # Use the participant_info we defined above
        "session_id": f"test-session-{int(asyncio.get_event_loop().time())}",  # Unique session ID
        "provider_keys": {
            "room_provider_key": daily_api_key,
        },
    }

    # Set the base URL for the hosted meeting page
    os.environ["MEET_BASE_URL"] = os.getenv("MEET_BASE_URL", "http://localhost:8001")

    print(f"\n{'='*80}")
    print("🚀 Creating room with bot enabled...")
    print(f"{'='*80}\n")

    # Show demo candidate info
    participant_info = context.get("participant_info", {})
    print("👤 Demo Candidate Information:")
    print(f"   Name: {participant_info.get('name', 'N/A')}")
    print(f"   Role: {participant_info.get('role', 'N/A')}")
    print(f"   Email: {participant_info.get('email', 'N/A')}")
    print(
        f"   Interview Type: {context.get('meeting_config', {}).get('interview_type', 'N/A')}\n"
    )

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
            print(f"   Then visit: http://localhost:8001/meet/{room_name}?bot=true\n")

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
