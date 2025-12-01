# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Process Transcript Step

This step handles the complete transcript processing pipeline:
1. Downloads transcript from Daily.co
2. Parses VTT format to extract text
3. Retrieves session data
4. Generates AI summary
5. Sends results via webhook/email
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict

import httpx
import resend

from flow.steps.interview.base import InterviewStep
from flow.steps.interview.extract_insights import ExtractInsightsStep
from flow.steps.interview.generate_summary import GenerateSummaryStep

logger = logging.getLogger(__name__)


# Helper Functions


def parse_vtt_to_text(vtt_content: str) -> str:
    """
    Parse VTT (WebVTT) format and extract plain text.

    Removes timestamps, metadata, and speaker labels to get just the text.
    """
    # Remove VTT header
    text = re.sub(r"^WEBVTT.*\n", "", vtt_content, flags=re.MULTILINE)

    # Remove timestamp lines (format: 00:00:00.000 --> 00:00:00.000)
    text = re.sub(
        r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*\n",
        "",
        text,
        flags=re.MULTILINE,
    )

    # Remove metadata lines (NOTE, STYLE, REGION)
    text = re.sub(r"^(NOTE|STYLE|REGION).*\n", "", text, flags=re.MULTILINE)

    # Remove speaker labels (<v Speaker>text</v>)
    text = re.sub(r"<v\s+[^>]+>", "", text)
    text = re.sub(r"</v>", "", text)

    # Remove empty lines and join
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return " ".join(lines)


def parse_transcript_to_qa_pairs(transcript_text: str) -> list[Dict[str, Any]]:
    """
    Parse transcript text to extract Q&A pairs.

    Args:
        transcript_text: Full transcript text with timestamps and role labels

    Returns:
        List of dictionaries with 'question' and 'answer' keys
    """
    qa_pairs = []
    lines = transcript_text.strip().split("\n")

    current_question = None
    current_answer_parts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match format: [timestamp] role: content
        # Or simpler: role: content (if no timestamp)
        # First try with timestamp: [timestamp] assistant: content
        match = re.match(r"^\[.*?\]\s*(assistant|user):\s*(.+)$", line, re.IGNORECASE)
        if match:
            role = match.group(1).lower()
            content = match.group(2)
        else:
            # Try without timestamp: assistant: content
            match = re.match(r"^(assistant|user):\s*(.+)$", line, re.IGNORECASE)
            if match:
                role = match.group(1).lower()
                content = match.group(2)
            else:
                # Skip lines that don't match the expected format
                continue

        if role and content:

            if role == "assistant":
                # If we have a previous question, save it as a Q&A pair
                if current_question and current_answer_parts:
                    qa_pairs.append(
                        {
                            "question": current_question,
                            "answer": " ".join(current_answer_parts).strip(),
                        }
                    )
                    current_answer_parts = []

                # Start new question
                current_question = content
            elif role == "user" and current_question:
                # Add to current answer
                current_answer_parts.append(content)

    # Don't forget the last pair
    if current_question and current_answer_parts:
        qa_pairs.append(
            {
                "question": current_question,
                "answer": " ".join(current_answer_parts).strip(),
            }
        )

    # Filter out pairs where question is just a greeting or answer is too short
    filtered_pairs = []
    for qa in qa_pairs:
        question = qa.get("question", "").lower()
        answer = qa.get("answer", "").strip()

        # Skip greetings and very short answers
        if any(
            greeting in question
            for greeting in ["hello", "thank you", "welcome", "goodbye", "bye"]
        ):
            if len(answer) < 20:  # Very short answers to greetings
                continue

        # Skip if answer is too short (likely not a real answer)
        if len(answer) < 10:
            continue

        filtered_pairs.append(qa)

    return filtered_pairs


async def get_daily_headers() -> dict[str, str]:
    """Get HTTP headers for Daily.co API requests."""
    api_key = os.getenv("DAILY_API_KEY", "")
    if not api_key:
        raise ValueError("DAILY_API_KEY environment variable is not set")

    auth_header = api_key.strip()
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }


async def get_transcript_download_link(transcript_id: str) -> str | None:
    """
    Get transcript download link from Daily.co API.

    According to Daily.co docs, the endpoint is: GET /v1/transcript/{id}/access-link (singular!)
    Response includes: { download_link }
    """
    try:
        headers = await get_daily_headers()

        async with httpx.AsyncClient() as client:
            # Fixed: Use correct endpoint - /v1/transcript/{id}/access-link (SINGULAR "transcript")
            response = await client.get(
                f"https://api.daily.co/v1/transcript/{transcript_id}/access-link",
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            # The download link is in the "link" field (not "download_link")
            return result.get("link")

    except Exception as e:
        logger.error(f"❌ Error getting transcript download link: {e}", exc_info=True)
        return None


async def download_transcript_vtt(download_link: str) -> str | None:
    """Download VTT transcript file from the access link."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(download_link)
            response.raise_for_status()
            return response.text

    except Exception as e:
        logger.error(f"❌ Error downloading VTT file: {e}", exc_info=True)
        return None


def get_room_session_data(room_name: str) -> dict[str, Any] | None:
    """
    Get session data from SQLite database.
    """
    from flow.db import get_session_data

    return get_session_data(room_name)


async def send_webhook(url: str, payload: dict[str, Any]) -> bool:
    """Send results to webhook URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
            logger.info(f"✅ Webhook sent to {url}")
            return True

    except Exception as e:
        logger.error(f"❌ Error sending webhook to {url}: {e}", exc_info=True)
        return False


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Send results via email using Resend.
    """
    try:
        # Get Resend API key from environment
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            logger.error("❌ RESEND_API_KEY environment variable is not set")
            return False

        # Get the verified email domain from environment
        email_domain = os.getenv("RESEND_EMAIL_DOMAIN")
        if not email_domain:
            logger.error("❌ RESEND_EMAIL_DOMAIN environment variable is not set")
            return False

        # Set the API key for Resend
        resend.api_key = api_key

        # Construct the "from" address using the verified domain
        # Using "noreply@" as a common pattern, but you can customize this
        from_email = f"PailKit <noreply@{email_domain}>"

        # Prepare email parameters
        # Convert body text to HTML (simple conversion - just wrap in <p> tags)
        html_body = body.replace("\n\n", "</p><p>").replace("\n", "<br>")
        html_body = f"<p>{html_body}</p>"

        params: resend.Emails.SendParams = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "reply_to": f"noreply@{email_domain}",
        }

        # Send the email (Resend's send() is synchronous, so we run it in an executor)
        # This prevents blocking the async event loop
        loop = asyncio.get_event_loop()
        email = await loop.run_in_executor(None, resend.Emails.send, params)
        logger.info(f"✅ Email sent successfully to {to_email}")
        logger.info(f"   Email ID: {email.get('id', 'N/A')}")
        return True

    except Exception as e:
        logger.error(f"❌ Error sending email to {to_email}: {e}", exc_info=True)
        return False


class ProcessTranscriptStep(InterviewStep):
    """
    Process transcript from Daily.co webhook.
    """

    def __init__(self):
        super().__init__(
            name="process_transcript",
            description="Download and process transcript from Daily.co",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute complete transcript processing pipeline.

        Args:
            state: Current workflow state containing:
                - transcript_id: ID from Daily.co webhook (optional if transcript_text in DB)
                - room_name: Room name for session data (required)
                - room_id: Room ID (optional)
                - duration: Duration in seconds (optional)

        Returns:
            Updated state with transcript_text, summary, and delivery status
        """
        logger.info("=" * 80)
        logger.info("🎬 Starting transcript processing pipeline")
        logger.info("=" * 80)

        # Validate required state - room_name is required, transcript_id is optional
        if not self.validate_state(state, ["room_name"]):
            return self.set_error(state, "Missing required field: room_name")

        transcript_id = state.get("transcript_id")
        room_name = state.get("room_name")
        room_id = state.get("room_id")
        duration = state.get("duration")

        logger.info(f"📋 Transcript ID: {transcript_id or 'N/A (using DB transcript)'}")
        logger.info(f"🏠 Room Name: {room_name}")

        try:
            # Step 1: Check if transcript exists in database (bot-enabled case)
            logger.info("\n📦 STEP 1: Checking database for transcript")
            session_data = get_room_session_data(room_name) if room_name else None
            transcript_text = None

            if session_data and session_data.get("transcript_text"):
                # Transcript exists in DB (bot was enabled)
                transcript_text = session_data.get("transcript_text")
                logger.info(
                    f"✅ Found transcript in database ({len(transcript_text)} chars)"
                )
                logger.info(
                    "   🤖 Using bot-generated transcript (includes both user and bot)"
                )
            else:
                # No transcript in DB - need to download from Daily.co
                logger.info(
                    "   📥 No transcript in database, will download from Daily.co"
                )

                if not transcript_id:
                    return self.set_error(
                        state,
                        "Missing transcript_id and no transcript_text in database. "
                        "Either bot must be enabled (saves to DB) or transcript_id must be provided.",
                    )

                # Step 2: Get transcript download link from Daily.co API
                logger.info(
                    "\n📥 STEP 2: Getting transcript download link from Daily.co"
                )
                download_link = await get_transcript_download_link(transcript_id)

                if not download_link:
                    return self.set_error(
                        state, "Failed to get transcript download link"
                    )

                logger.info("✅ Got download link")

                # Step 3: Download VTT file
                logger.info("\n📄 STEP 3: Downloading VTT file")
                vtt_content = await download_transcript_vtt(download_link)

                if not vtt_content:
                    return self.set_error(state, "Failed to download VTT file")

                logger.info(f"✅ Downloaded VTT ({len(vtt_content)} chars)")

                # Step 4: Parse VTT to extract text
                logger.info("\n🔤 STEP 4: Extracting text from VTT")
                transcript_text = parse_vtt_to_text(vtt_content)
                logger.info(f"✅ Extracted text ({len(transcript_text)} chars)")

            # Store transcript in state
            state["interview_transcript"] = transcript_text

            # Step 5: Retrieve session data from SQLite database (if not already retrieved)
            logger.info("\n📦 STEP 5: Retrieving session data from database")
            if not session_data:
                session_data = get_room_session_data(room_name) if room_name else None

            if not session_data:
                logger.warning("⚠️ No session data found")
                session_data = {}

            # Check if transcript was already processed to prevent duplicate processing
            transcript_already_processed = session_data.get(
                "transcript_processed", False
            )
            if transcript_already_processed:
                logger.warning(
                    "⚠️ Transcript was already processed for this room - skipping duplicate processing"
                )
                logger.info(
                    "   If you need to reprocess, clear the transcript_processed flag in session_data"
                )
                state = self.update_status(state, "already_completed")
                return state

            webhook_callback_url = session_data.get("webhook_callback_url")
            email_results_to = session_data.get("email_results_to")
            candidate_name = session_data.get("candidate_name", "Unknown")
            position = session_data.get("position", "Unknown")
            interview_type = session_data.get("interview_type", "Interview")
            interviewer_context = session_data.get("interviewer_context", "")

            logger.info(f"   👤 Candidate: {candidate_name}")
            logger.info(f"   💼 Position: {position}")
            logger.info(f"   📋 Interview Type: {interview_type}")

            # Check if we already sent email to prevent duplicates
            email_already_sent = session_data.get("email_sent", False)
            if email_already_sent:
                logger.warning(
                    "⚠️ Email was already sent for this room - skipping duplicate send"
                )

            # Build participant_info from session_data
            # Note: session_data uses "candidate_name" for backwards compatibility with existing DB records
            participant_info = {
                "name": candidate_name,
                "role": position,
                "email": session_data.get("candidate_email"),
            }
            state["participant_info"] = participant_info

            # Store interview metadata for summary
            state["interview_type"] = interview_type
            state["interviewer_context"] = interviewer_context

            # Get prompts from session_data (passed from meeting_config)
            analysis_prompt = session_data.get("analysis_prompt")
            summary_format_prompt = session_data.get("summary_format_prompt")

            # Build meeting_config with prompts for steps to access
            state["meeting_config"] = {
                "analysis_prompt": analysis_prompt,
                "summary_format_prompt": summary_format_prompt,
            }

            # Also store in interview_config for backwards compatibility
            state["interview_config"] = {
                "interview_type": interview_type,
                "interviewer_context": interviewer_context,
                "analysis_prompt": analysis_prompt,
                "summary_format_prompt": summary_format_prompt,
            }

            # Step 6: Parse transcript to extract Q&A pairs
            logger.info("\n📝 STEP 6: Parsing transcript to extract Q&A pairs")
            qa_pairs = parse_transcript_to_qa_pairs(transcript_text)
            logger.info(f"✅ Extracted {len(qa_pairs)} Q&A pairs from transcript")

            if not qa_pairs:
                logger.warning(
                    "⚠️ No Q&A pairs found in transcript - using full transcript as fallback"
                )
                qa_pairs = [
                    {
                        "question": "Full Interview Transcript",
                        "answer": transcript_text,
                    }
                ]

            state["qa_pairs"] = qa_pairs

            # Step 7: Extract insights using AI analysis
            logger.info("\n🧠 STEP 7: Extracting insights and assessing competencies")
            extract_insights_step = ExtractInsightsStep()
            state = await extract_insights_step.execute(state)

            if state.get("error"):
                logger.error(f"❌ Error extracting insights: {state.get('error')}")
                # Continue anyway with placeholder insights
                state["insights"] = {
                    "overall_score": 0.0,
                    "competency_scores": {},
                    "strengths": ["Analysis pending"],
                    "weaknesses": ["Analysis pending"],
                }
            else:
                logger.info("✅ Insights extracted successfully")

            # Step 8: Generate AI summary
            logger.info("\n🤖 STEP 8: Generating AI summary")
            summary_step = GenerateSummaryStep()
            state = await summary_step.execute(state)

            if state.get("error"):
                return state

            candidate_summary = state.get("candidate_summary", "")
            logger.info(f"✅ Summary generated ({len(candidate_summary)} chars)")

            # Step 9: Send results
            logger.info("\n📤 STEP 9: Sending results")

            results_payload = {
                "event": "interview_complete",
                "transcript_id": transcript_id,
                "room_id": room_id,
                "room_name": room_name,
                "candidate_name": candidate_name,
                "position": position,
                "duration_seconds": duration,
                "transcript_text": transcript_text,
                "candidate_summary": candidate_summary,
                "insights": state.get("insights"),
            }

            # Send webhook
            webhook_sent = False
            if webhook_callback_url:
                logger.info(f"🔗 Sending webhook to: {webhook_callback_url}")
                webhook_sent = await send_webhook(webhook_callback_url, results_payload)

            state["webhook_sent"] = webhook_sent

            # Send email (only if not already sent)
            email_sent = False
            if email_results_to and not email_already_sent:
                logger.info(f"📧 Sending email to: {email_results_to}")
                logger.info(
                    f"   Subject: Interview Complete: {candidate_name} - {position}"
                )
                subject = f"Interview Complete: {candidate_name} - {position}"
                body = f"{candidate_summary}\n\nFull Transcript:\n{transcript_text}"
                email_sent = await send_email(email_results_to, subject, body)

                # Mark as sent in session_data to prevent duplicates
                if email_sent and room_name:
                    from flow.db import get_session_data, save_session_data

                    current_session = get_session_data(room_name) or {}
                    current_session["email_sent"] = True
                    save_session_data(room_name, current_session)
            elif email_already_sent:
                logger.info("📧 Email already sent - skipping duplicate")
            elif not email_results_to:
                logger.info("📧 No email address configured - skipping email")

            state["email_sent"] = email_sent

            # Mark transcript as processed to prevent duplicate processing
            if room_name:
                from flow.db import get_session_data, save_session_data

                current_session = get_session_data(room_name) or {}
                current_session["transcript_processed"] = True
                save_session_data(room_name, current_session)
                logger.info("✅ Marked transcript as processed to prevent duplicates")

            state = self.update_status(state, "completed")

            logger.info("\n" + "=" * 80)
            logger.info("✅ TRANSCRIPT PROCESSING COMPLETE")
            logger.info("=" * 80)

            return state

        except Exception as e:
            error_msg = f"Transcript processing failed: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return self.set_error(state, error_msg)
