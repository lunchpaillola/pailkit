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
import html
import json
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
    Get session data from Supabase database.
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


def format_json_summary_html(summary_json: Dict[str, Any]) -> str:
    """
    Format a JSON summary (like lead qualification) into clean HTML.

    Shows key information at the top, then recommendation.
    """
    html_parts = []

    # Extract lead information if present (skip the call_name header)
    lead_info = summary_json.get("lead", {})
    if isinstance(lead_info, dict) and lead_info:
        html_parts.append(
            '<div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin-bottom: 24px;">'
        )
        html_parts.append(
            '<h3 style="color: #1e293b; font-size: 16px; font-weight: 600; margin: 0 0 16px 0;">Lead Information</h3>'
        )

        # Format key-value pairs
        fields = [
            ("Name", lead_info.get("name")),
            ("Problem", lead_info.get("problem")),
            ("Current Workaround", lead_info.get("current_workaround")),
            ("Timeline", lead_info.get("timeline")),
            ("Budget", lead_info.get("budget")),
            ("Decision Maker", lead_info.get("decision_maker")),
        ]

        for label, value in fields:
            if value and value != "Not specified" and value != "Unknown":
                escaped_value = html.escape(str(value))
                html_parts.append(
                    f'<div style="margin-bottom: 12px;">'
                    f'<div style="font-weight: 600; color: #475569; font-size: 13px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">{html.escape(label)}</div>'
                    f'<div style="color: #1e293b; font-size: 15px; line-height: 1.5;">{escaped_value}</div>'
                    f"</div>"
                )

        # Show fit score if available
        fit_score = lead_info.get("quick_fit_score")
        if fit_score is not None:
            score_value = float(fit_score) if fit_score else 0.0
            score_color = (
                "#10b981"
                if score_value >= 7
                else "#f59e0b" if score_value >= 4 else "#ef4444"
            )
            html_parts.append(
                f'<div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #e2e8f0;">'
                f'<div style="font-weight: 600; color: #475569; font-size: 13px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">Quick Fit Score</div>'
                f'<div style="color: {score_color}; font-size: 24px; font-weight: 700; line-height: 1.2;">{score_value:.1f}/10</div>'
                f"</div>"
            )

        html_parts.append("</div>")

    # Show recommendation if present
    recommendation = summary_json.get("recommendation")
    if recommendation:
        html_parts.append(
            f'<div style="background-color: #f0f4ff; padding: 20px; border-radius: 6px; border-left: 4px solid #1f2de6; margin-top: 24px;">'
            f'<div style="font-weight: 600; color: #1f2de6; font-size: 13px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Recommendation</div>'
            f'<div style="color: #1e293b; font-size: 15px; line-height: 1.6;">{html.escape(str(recommendation))}</div>'
            f"</div>"
        )

    return "\n".join(html_parts)


def format_transcript_html(transcript_text: str) -> str:
    """
    Format transcript text into HTML with alternating speaker colors.

    This function parses the transcript and formats it nicely:
    - Alternating background colors for assistant vs user messages
    - Timestamps styled subtly
    - Clear speaker labels
    """
    if not transcript_text:
        return "<p><em>No transcript available</em></p>"

    lines = transcript_text.strip().split("\n")
    html_parts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match format: [timestamp] role: content
        # Or simpler: role: content (if no timestamp)
        timestamp_match = re.match(
            r"^\[(.+?)\]\s*(assistant|user):\s*(.+)$", line, re.IGNORECASE
        )
        if timestamp_match:
            timestamp = timestamp_match.group(1)
            role = timestamp_match.group(2).lower()
            content = timestamp_match.group(3)
        else:
            # Try without timestamp
            role_match = re.match(r"^(assistant|user):\s*(.+)$", line, re.IGNORECASE)
            if role_match:
                timestamp = None
                role = role_match.group(1).lower()
                content = role_match.group(2)
            else:
                # Plain text line - escape and add it
                escaped_line = html.escape(line)
                html_parts.append(f"<p>{escaped_line}</p>")
                continue

        # Determine speaker label and styling (using brand colors)
        if role == "assistant":
            speaker_label = "Assistant"
            bg_color = "#f0f4ff"
            border_color = "#1f2de6"
        else:
            speaker_label = "User"
            bg_color = "#f8f9fa"
            border_color = "#64748b"

        # Build HTML for this message
        message_html = '<div style="margin-bottom: 12px; padding: 12px; background-color: {}; border-left: 3px solid {}; border-radius: 4px;">'.format(
            bg_color, border_color
        )

        # Add speaker label and timestamp
        header_style = "font-weight: 600; color: {}; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;".format(
            border_color
        )
        message_html += f'<div style="{header_style}">{speaker_label}'
        if timestamp:
            # Format timestamp nicely (remove timezone if present)
            clean_timestamp = timestamp.split("+")[0].split(".")[
                0
            ]  # Remove timezone and milliseconds
            message_html += f' <span style="font-weight: 400; opacity: 0.7;">({clean_timestamp})</span>'
        message_html += "</div>"

        # Add content (escape HTML to prevent XSS)
        escaped_content = html.escape(content)
        message_html += (
            f'<div style="color: #334155; line-height: 1.6;">{escaped_content}</div>'
        )
        message_html += "</div>"

        html_parts.append(message_html)

    return "\n".join(html_parts)


def convert_markdown_to_html(text: str) -> str:
    """
    Convert basic Markdown formatting to HTML.

    Handles:
    - **bold** -> <strong>bold</strong>
    - *italic* -> <em>italic</em>
    - ## Header -> <h2>Header</h2>
    - ### Header -> <h3>Header</h3>
    - - list item -> <li>list item</li>
    """
    # Convert bold (**text** or __text__)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)

    # Convert italic (*text* or _text_)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<em>\1</em>", text)

    return text


def format_summary_html(summary_text: str) -> str:
    """
    Format summary text into HTML with proper section styling.

    This function converts the plain text summary into nicely formatted HTML:
    - JSON summaries are formatted as clean key-value pairs
    - Markdown formatting is converted to HTML
    - Headers are styled as section titles
    - Lists are properly formatted
    - Scores and metrics are highlighted
    """
    if not summary_text:
        return "<p><em>No summary available</em></p>"

    # Check if summary is JSON and format it nicely
    # Try to detect JSON by checking if it starts with { or [ and can be parsed
    summary_text_stripped = summary_text.strip()
    if summary_text_stripped.startswith("{") or summary_text_stripped.startswith("["):
        try:
            summary_json = json.loads(summary_text_stripped)
            if isinstance(summary_json, dict):
                logger.debug("Detected JSON summary, formatting as HTML")
                return format_json_summary_html(summary_json)
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            # Not valid JSON, continue with regular text formatting
            logger.debug(f"Summary is not valid JSON: {e}, using text formatting")
            pass

    lines = summary_text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        line = line.strip()

        # Skip empty lines (but close lists if needed)
        if not line:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        # Check for section headers (lines with === or all caps)
        if line.startswith("=" * 30):
            # Section divider - skip it, we'll style the next line as a header
            continue

        # Check if this looks like a header (all caps, short, or followed by ===)
        is_header = (
            line.isupper()
            and len(line) < 80
            and not line.startswith("Q:")
            and not line.startswith("A:")
        ) or line.endswith(":")

        # Check for Markdown headers (## Header or ### Header)
        markdown_header_match = re.match(r"^#{1,3}\s+(.+)$", line)
        if markdown_header_match:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            header_text = markdown_header_match.group(1).strip()
            header_level = len(line) - len(line.lstrip("#"))
            escaped_header = html.escape(header_text)
            # Convert any markdown in header text
            escaped_header = convert_markdown_to_html(escaped_header)
            if header_level == 1:
                html_parts.append(
                    f'<h2 style="color: #1e293b; font-size: 20px; font-weight: 600; margin: 24px 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">{escaped_header}</h2>'
                )
            elif header_level == 2:
                html_parts.append(
                    f'<h3 style="color: #1e293b; font-size: 18px; font-weight: 600; margin: 20px 0 10px 0;">{escaped_header}</h3>'
                )
            else:
                html_parts.append(
                    f'<h4 style="color: #1e293b; font-size: 16px; font-weight: 600; margin: 16px 0 8px 0;">{escaped_header}</h4>'
                )
            continue

        # Check for Markdown list items (- item or * item)
        markdown_list_match = re.match(r"^[-*]\s+(.+)$", line)
        if markdown_list_match:
            if not in_list:
                html_parts.append('<ul style="margin: 12px 0; padding-left: 24px;">')
                in_list = True
            item_text = markdown_list_match.group(1).strip()
            # Escape HTML first, then convert markdown
            escaped_item = html.escape(item_text)
            escaped_item = convert_markdown_to_html(escaped_item)
            html_parts.append(
                f'<li style="margin-bottom: 8px; line-height: 1.6;">{escaped_item}</li>'
            )
            continue

        # Check for numbered list items
        list_match = re.match(r"^(\d+)\.\s+(.+)$", line)

        # Check for Q&A format
        qa_match = re.match(r"^(Q|A|Question \d+):\s*(.+)$", line, re.IGNORECASE)

        if list_match:
            if not in_list:
                html_parts.append('<ul style="margin: 12px 0; padding-left: 24px;">')
                in_list = True
            item_text = html.escape(list_match.group(2))
            # Convert markdown in numbered list items too
            item_text = convert_markdown_to_html(item_text)
            html_parts.append(
                f'<li style="margin-bottom: 8px; line-height: 1.6;">{item_text}</li>'
            )
        elif qa_match:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            qa_type = html.escape(qa_match.group(1))
            qa_content = html.escape(qa_match.group(2))
            if qa_type.upper().startswith("Q"):
                html_parts.append(
                    f'<div style="margin: 16px 0 8px 0;"><strong style="color: #1f2de6;">{qa_type}:</strong> <span style="color: #1e293b;">{qa_content}</span></div>'
                )
            else:
                html_parts.append(
                    f'<div style="margin: 0 0 16px 20px; padding: 8px; background-color: #f8f9fa; border-left: 2px solid #e2e8f0; color: #475569;">{qa_content}</div>'
                )
        elif is_header and len(line) < 100:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Style as section header (using brand colors)
            escaped_header = html.escape(line)
            html_parts.append(
                f'<h2 style="color: #1e293b; font-size: 18px; font-weight: 600; margin: 24px 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">{escaped_header}</h2>'
            )
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Regular paragraph
            # Escape HTML first, then convert markdown, then highlight scores
            escaped_line = html.escape(line)
            # Convert markdown formatting (bold, italic)
            formatted_line = convert_markdown_to_html(escaped_line)
            # Highlight scores (e.g., "8.5/10" or "Score: 7.0")
            formatted_line = re.sub(
                r"(\d+\.?\d*)/10",
                r'<span style="background-color: #fff3cd; padding: 2px 6px; border-radius: 3px; font-weight: 600;">\1/10</span>',
                formatted_line,
            )
            formatted_line = re.sub(
                r"Score:\s*(\d+\.?\d*)",
                r'Score: <span style="background-color: #fff3cd; padding: 2px 6px; border-radius: 3px; font-weight: 600;">\1</span>',
                formatted_line,
            )
            html_parts.append(
                f'<p style="margin: 8px 0; line-height: 1.6; color: #334155;">{formatted_line}</p>'
            )

    # Close any open list
    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def generate_html_email(
    summary_text: str,
    transcript_text: str,
    candidate_name: str = "Unknown",
    interview_type: str = "Interview",
    insights: Dict[str, Any] | None = None,
) -> str:
    """
    Generate a beautiful HTML email from summary and transcript.

    This function creates a professional-looking HTML email with:
    - A clean header matching PailFlow branding
    - Formatted summary sections
    - Nicely styled transcript with speaker differentiation
    - Responsive design that works in email clients
    """
    # Format the summary and transcript
    summary_html = format_summary_html(summary_text)
    transcript_html = format_transcript_html(transcript_text)

    # Use sensible defaults if values are missing
    if not interview_type or interview_type == "Unknown":
        interview_type = "Session"
    if not candidate_name:
        candidate_name = "Unknown"

    # Escape user-provided content for security
    escaped_interview_type = html.escape(str(interview_type))
    escaped_candidate_name = html.escape(str(candidate_name))

    # Build the complete HTML email
    # Use brand colors: #1f2de6 (brand blue), clean flat design
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escaped_interview_type} Results</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8f9fa;">
    <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f8f9fa; padding: 20px;">
        <tr>
            <td align="center">
                <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: #ffffff; border-radius: 0; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <!-- Top Brand Line -->
                    <tr>
                        <td style="height: 4px; background-color: #1f2de6; width: 100%;"></td>
                    </tr>
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 32px 24px 24px 24px; border-bottom: 1px solid #e2e8f0;">
                            <div style="margin-bottom: 16px;">
                                <div style="font-weight: 700; font-size: 18px; line-height: 1.2; color: #1e293b; letter-spacing: -0.01em;">PailFlow</div>
                                <div style="font-size: 10px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 2px;">Workspace</div>
                            </div>
                            <h1 style="margin: 0; color: #1e293b; font-size: 22px; font-weight: 600; line-height: 1.3;">{escaped_interview_type} Complete</h1>
                            {f'<p style="margin: 8px 0 0 0; color: #64748b; font-size: 14px; line-height: 1.5;">{escaped_candidate_name}</p>' if escaped_candidate_name and escaped_candidate_name != "Unknown" else ''}
                        </td>
                    </tr>

                    <!-- Summary Section -->
                    <tr>
                        <td style="padding: 32px 24px;">
                            <div style="margin-bottom: 0;">
                                {summary_html}
                            </div>
                        </td>
                    </tr>

                    <!-- Transcript Section -->
                    <tr>
                        <td style="padding: 0 24px 32px 24px;">
                            <h2 style="color: #1e293b; font-size: 18px; font-weight: 600; margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">Full Transcript</h2>
                            <div style="max-height: 600px; overflow-y: auto; padding: 16px; background-color: #f8f9fa; border-radius: 6px; border: 1px solid #e2e8f0;">
                                {transcript_html}
                            </div>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 24px; text-align: center; background-color: #ffffff; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0; color: #94a3b8; font-size: 12px; font-weight: 500;">Sent by PailFlow</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    return html_content


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    candidate_name: str = "Unknown",
    interview_type: str = "Interview",
    transcript_text: str = "",
    insights: Dict[str, Any] | None = None,
) -> bool:
    """
    Send results via email using Resend with beautiful HTML formatting.

    This function now generates a professional HTML email instead of plain text.
    The body parameter is treated as the summary text, and transcript_text is
    formatted separately for better presentation.
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
        from_email = f"PailFlow <noreply@{email_domain}>"

        # Generate beautiful HTML email
        html_body = generate_html_email(
            summary_text=body,
            transcript_text=transcript_text,
            candidate_name=candidate_name,
            interview_type=interview_type,
            insights=insights,
        )

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

            # Step 5: Retrieve session data from Supabase database (if not already retrieved)
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

            # For lead qualification, the name might be extracted in insights as person_name
            # We'll check insights later after they're extracted and update candidate_name if needed

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

                # For lead qualification, try to extract name from insights if available
                # The insights might have person_name (from lead qualification) or the name might be in the summary JSON
                email_candidate_name = (
                    candidate_name
                    if candidate_name and candidate_name != "Unknown"
                    else "Unknown"
                )
                insights = state.get("insights", {})

                # Check if insights has person_name (for lead qualification flows)
                if insights and isinstance(insights, dict):
                    extracted_name = insights.get("person_name")
                    if (
                        extracted_name
                        and extracted_name != "Unknown"
                        and extracted_name.strip()
                    ):
                        email_candidate_name = extracted_name
                        logger.info(
                            f"   📝 Using extracted name from insights: {email_candidate_name}"
                        )

                # Also try to extract from summary JSON if it's a lead qualification summary
                # The summary might be JSON with lead.name field
                if email_candidate_name == "Unknown" and candidate_summary:
                    try:
                        # Try to parse JSON from summary (lead qualification summaries are JSON)
                        summary_json = json.loads(candidate_summary.strip())
                        if isinstance(summary_json, dict):
                            lead_info = summary_json.get("lead", {})
                            if isinstance(lead_info, dict):
                                lead_name = lead_info.get("name")
                                if (
                                    lead_name
                                    and lead_name != "Unknown"
                                    and lead_name.strip()
                                ):
                                    email_candidate_name = lead_name
                                    logger.info(
                                        f"   📝 Using extracted name from summary JSON: {email_candidate_name}"
                                    )
                    except (json.JSONDecodeError, AttributeError):
                        # Summary is not JSON, that's fine - use the name we have
                        pass

                # Ensure we have valid values (not None)
                email_candidate_name = (
                    email_candidate_name if email_candidate_name else "Unknown"
                )

                # If we have a valid name (not "Unknown"), update the summary JSON/text to replace "Unknown" with the actual name
                # This ensures the email body shows the correct name, not "Unknown"
                email_summary = candidate_summary
                if email_candidate_name != "Unknown" and candidate_summary:
                    try:
                        # Try to parse and update JSON summary (for lead qualification)
                        summary_json = json.loads(candidate_summary.strip())
                        if isinstance(summary_json, dict):
                            # Check if there's a lead.name field that needs updating
                            lead_info = summary_json.get("lead", {})
                            if (
                                isinstance(lead_info, dict)
                                and lead_info.get("name") == "Unknown"
                            ):
                                # Update the name in the JSON
                                summary_json["lead"]["name"] = email_candidate_name
                                # Re-serialize the JSON with proper formatting
                                email_summary = json.dumps(summary_json, indent=2)
                                logger.info(
                                    f"   📝 Updated summary JSON to use name: {email_candidate_name}"
                                )
                            # Also check for other name fields that might be "Unknown"
                            elif (
                                "name" in summary_json
                                and summary_json.get("name") == "Unknown"
                            ):
                                summary_json["name"] = email_candidate_name
                                email_summary = json.dumps(summary_json, indent=2)
                                logger.info(
                                    f"   📝 Updated summary JSON name field: {email_candidate_name}"
                                )
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        # Summary is not JSON or couldn't be updated, try text replacement
                        if "Unknown" in candidate_summary:
                            # Replace "Unknown" with the extracted name in the summary text
                            # Be careful to only replace when it's clearly a name field
                            email_summary = candidate_summary.replace(
                                '"name": "Unknown"', f'"name": "{email_candidate_name}"'
                            )
                            email_summary = email_summary.replace(
                                "name: Unknown", f"name: {email_candidate_name}"
                            )
                            email_summary = email_summary.replace(
                                "Participant: Unknown",
                                f"Participant: {email_candidate_name}",
                            )
                            email_summary = email_summary.replace(
                                "Candidate: Unknown",
                                f"Candidate: {email_candidate_name}",
                            )
                            logger.info(
                                f"   📝 Updated summary text to use name: {email_candidate_name}"
                            )

                # Generate appropriate subject based on interview_type
                # For lead qualification, use "Qualification Complete", otherwise use interview_type
                is_qualification = (
                    interview_type and "qualification" in interview_type.lower()
                )
                if is_qualification:
                    subject_prefix = "Qualification Complete"
                elif interview_type and interview_type != "Interview":
                    subject_prefix = interview_type + " Complete"
                else:
                    subject_prefix = "Session Complete"

                # Build subject with name and position/role (use extracted name if available)
                # For qualification calls, don't include position (it's usually just "Lead")
                # For other calls, include position if it's meaningful
                if is_qualification:
                    # For qualification: just use name
                    subject = f"{subject_prefix}: {email_candidate_name}"
                elif position and position != "Unknown" and position != "Lead":
                    # For interviews: include position if it's meaningful
                    subject = f"{subject_prefix}: {email_candidate_name} - {position}"
                else:
                    # Fallback: just use name
                    subject = f"{subject_prefix}: {email_candidate_name}"

                logger.info(f"   Subject: {subject}")

                email_interview_type = interview_type if interview_type else "Session"
                email_transcript = transcript_text if transcript_text else ""

                email_sent = await send_email(
                    to_email=email_results_to,
                    subject=subject,
                    body=email_summary,  # Summary text (may have been updated with extracted name)
                    candidate_name=email_candidate_name,
                    interview_type=email_interview_type,
                    transcript_text=email_transcript,  # Transcript formatted separately
                    insights=insights,  # Include insights for potential JSON formatting
                )

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
