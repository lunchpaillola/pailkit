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

    **Simple Explanation:**
    This function calls the Daily.co API to get transcript access link.
    The API returns a JSON object that includes a 'download_link' field
    which points to the actual VTT file we need to download.

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

    **Simple Explanation:**
    This function retrieves session data from our local SQLite database
    using the room_name as the key. The session data was saved when the
    room was created and includes candidate info, webhook URLs, etc.
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

    **Simple Explanation:**
    This function uses the Resend email service to send emails. It:
    1. Gets the API key from environment variables
    2. Gets the verified email domain from environment variables
    3. Constructs the email with a "from" address using that domain
    4. Sends the email with the provided subject and body (as HTML)
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

    **Simple Explanation:**
    This step is triggered when Daily.co sends a webhook saying a transcript
    is ready. It handles the complete workflow:
    - Downloads the transcript from Daily.co
    - Extracts text from VTT format
    - Retrieves session data (candidate info, webhook URLs, etc.)
    - Generates an AI-powered summary
    - Sends results via webhook and/or email
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
                - transcript_id: ID from Daily.co webhook
                - room_name: Room name for session data
                - room_id: Room ID (optional)
                - duration: Duration in seconds (optional)

        Returns:
            Updated state with transcript_text, summary, and delivery status
        """
        logger.info("=" * 80)
        logger.info("🎬 Starting transcript processing pipeline")
        logger.info("=" * 80)

        # Validate required state
        if not self.validate_state(state, ["transcript_id"]):
            return self.set_error(state, "Missing required field: transcript_id")

        transcript_id = state.get("transcript_id")
        room_name = state.get("room_name")
        room_id = state.get("room_id")
        duration = state.get("duration")

        logger.info(f"📋 Transcript ID: {transcript_id}")
        logger.info(f"🏠 Room Name: {room_name}")

        try:
            # Step 1: Get transcript download link from Daily.co API
            logger.info("\n📥 STEP 1: Getting transcript download link")
            download_link = await get_transcript_download_link(transcript_id)

            if not download_link:
                return self.set_error(state, "Failed to get transcript download link")

            logger.info("✅ Got download link")

            # Step 2: Download VTT file
            logger.info("\n📄 STEP 2: Downloading VTT file")
            vtt_content = await download_transcript_vtt(download_link)

            if not vtt_content:
                return self.set_error(state, "Failed to download VTT file")

            logger.info(f"✅ Downloaded VTT ({len(vtt_content)} chars)")

            # Step 3: Parse VTT to extract text
            logger.info("\n🔤 STEP 3: Extracting text from VTT")
            transcript_text = parse_vtt_to_text(vtt_content)
            logger.info(f"✅ Extracted text ({len(transcript_text)} chars)")

            state["interview_transcript"] = transcript_text

            # Step 4: Retrieve session data from SQLite database
            logger.info("\n📦 STEP 4: Retrieving session data from database")
            session_data = get_room_session_data(room_name) if room_name else None

            if not session_data:
                logger.warning("⚠️ No session data found")
                session_data = {}

            webhook_callback_url = session_data.get("webhook_callback_url")
            email_results_to = session_data.get("email_results_to")
            candidate_name = session_data.get("candidate_name", "Unknown")
            position = session_data.get("position", "Unknown")

            logger.info(f"   👤 Candidate: {candidate_name}")
            logger.info(f"   💼 Position: {position}")

            state["candidate_info"] = {
                "name": candidate_name,
                "role": position,
                "email": session_data.get("candidate_email"),
            }

            # Step 5: Generate AI summary
            logger.info("\n🤖 STEP 5: Generating AI summary")

            # Add required fields for summary generation
            state["insights"] = {
                "overall_score": 0.0,
                "competency_scores": {},
                "strengths": ["To be analyzed from transcript"],
                "weaknesses": ["To be analyzed from transcript"],
            }
            state["qa_pairs"] = [
                {
                    "question": "See full transcript",
                    "answer": transcript_text[:500] + "...",
                }
            ]

            summary_step = GenerateSummaryStep()
            state = await summary_step.execute(state)

            if state.get("error"):
                return state

            candidate_summary = state.get("candidate_summary", "")
            logger.info(f"✅ Summary generated ({len(candidate_summary)} chars)")

            # Step 6: Send results
            logger.info("\n📤 STEP 6: Sending results")

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

            # Send email
            email_sent = False
            if email_results_to:
                logger.info(f"📧 Sending email to: {email_results_to}")
                subject = f"Interview Complete: {candidate_name} - {position}"
                body = f"{candidate_summary}\n\nFull Transcript:\n{transcript_text}"
                email_sent = await send_email(email_results_to, subject, body)

            state["email_sent"] = email_sent

            state = self.update_status(state, "completed")

            logger.info("\n" + "=" * 80)
            logger.info("✅ TRANSCRIPT PROCESSING COMPLETE")
            logger.info("=" * 80)

            return state

        except Exception as e:
            error_msg = f"Transcript processing failed: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return self.set_error(state, error_msg)
