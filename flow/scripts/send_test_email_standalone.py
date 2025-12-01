#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Standalone test email script - sends a test email without importing full flow dependencies.
"""

import asyncio
import html
import json
import os
import re
from typing import Any, Dict
from dotenv import load_dotenv

import resend


def format_transcript_html(transcript_text: str) -> str:
    """Format transcript text into HTML with alternating speaker colors."""
    if not transcript_text:
        return "<p><em>No transcript available</em></p>"

    lines = transcript_text.strip().split("\n")
    html_parts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        timestamp_match = re.match(
            r"^\[(.+?)\]\s*(assistant|user):\s*(.+)$", line, re.IGNORECASE
        )
        if timestamp_match:
            timestamp = timestamp_match.group(1)
            role = timestamp_match.group(2).lower()
            content = timestamp_match.group(3)
        else:
            role_match = re.match(r"^(assistant|user):\s*(.+)$", line, re.IGNORECASE)
            if role_match:
                timestamp = None
                role = role_match.group(1).lower()
                content = role_match.group(2)
            else:
                escaped_line = html.escape(line)
                html_parts.append(f"<p>{escaped_line}</p>")
                continue

        if role == "assistant":
            speaker_label = "Assistant"
            bg_color = "#f0f4ff"
            border_color = "#1f2de6"
        else:
            speaker_label = "User"
            bg_color = "#f8f9fa"
            border_color = "#64748b"

        message_html = '<div style="margin-bottom: 12px; padding: 12px; background-color: {}; border-left: 3px solid {}; border-radius: 4px;">'.format(
            bg_color, border_color
        )

        header_style = "font-weight: 600; color: {}; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;".format(
            border_color
        )
        message_html += f'<div style="{header_style}">{speaker_label}'
        if timestamp:
            clean_timestamp = timestamp.split("+")[0].split(".")[0]
            message_html += f' <span style="font-weight: 400; opacity: 0.7;">({clean_timestamp})</span>'
        message_html += "</div>"

        escaped_content = html.escape(content)
        message_html += (
            f'<div style="color: #334155; line-height: 1.6;">{escaped_content}</div>'
        )
        message_html += "</div>"

        html_parts.append(message_html)

    return "\n".join(html_parts)


def format_json_summary_html(summary_json: Dict[str, Any]) -> str:
    """Format a JSON summary (like lead qualification) into clean HTML."""
    html_parts = []

    # Start directly with Lead Information (skip the call_name header)
    lead_info = summary_json.get("lead", {})
    if isinstance(lead_info, dict) and lead_info:
        html_parts.append(
            '<div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin-bottom: 24px;">'
        )
        html_parts.append(
            '<h3 style="color: #1e293b; font-size: 16px; font-weight: 600; margin: 0 0 16px 0;">Lead Information</h3>'
        )

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

    recommendation = summary_json.get("recommendation")
    if recommendation:
        html_parts.append(
            f'<div style="background-color: #f0f4ff; padding: 20px; border-radius: 6px; border-left: 4px solid #1f2de6; margin-top: 24px;">'
            f'<div style="font-weight: 600; color: #1f2de6; font-size: 13px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Recommendation</div>'
            f'<div style="color: #1e293b; font-size: 15px; line-height: 1.6;">{html.escape(str(recommendation))}</div>'
            f"</div>"
        )

    return "\n".join(html_parts)


def format_summary_html(summary_text: str) -> str:
    """Format summary text into HTML with proper section styling."""
    if not summary_text:
        return "<p><em>No summary available</em></p>"

    # Check if summary is JSON and format it nicely
    try:
        summary_json = json.loads(summary_text.strip())
        if isinstance(summary_json, dict):
            return format_json_summary_html(summary_json)
    except (json.JSONDecodeError, AttributeError, TypeError):
        # Not JSON, continue with regular text formatting
        pass

    lines = summary_text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        line = line.strip()

        if not line:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if line.startswith("=" * 30):
            continue

        is_header = (
            line.isupper()
            and len(line) < 80
            and not line.startswith("Q:")
            and not line.startswith("A:")
        ) or line.endswith(":")

        list_match = re.match(r"^(\d+)\.\s+(.+)$", line)
        qa_match = re.match(r"^(Q|A|Question \d+):\s*(.+)$", line, re.IGNORECASE)

        if list_match:
            if not in_list:
                html_parts.append('<ul style="margin: 12px 0; padding-left: 24px;">')
                in_list = True
            item_text = html.escape(list_match.group(2))
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
            escaped_header = html.escape(line)
            html_parts.append(
                f'<h2 style="color: #1e293b; font-size: 18px; font-weight: 600; margin: 24px 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;">{escaped_header}</h2>'
            )
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            escaped_line = html.escape(line)
            formatted_line = re.sub(
                r"(\d+\.?\d*)/10",
                r'<span style="background-color: #fff3cd; padding: 2px 6px; border-radius: 3px; font-weight: 600;">\1/10</span>',
                escaped_line,
            )
            formatted_line = re.sub(
                r"Score:\s*(\d+\.?\d*)",
                r'Score: <span style="background-color: #fff3cd; padding: 2px 6px; border-radius: 3px; font-weight: 600;">\1</span>',
                formatted_line,
            )
            html_parts.append(
                f'<p style="margin: 8px 0; line-height: 1.6; color: #334155;">{formatted_line}</p>'
            )

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def generate_html_email(
    summary_text: str,
    transcript_text: str,
    candidate_name: str = "Unknown",
    interview_type: str = "Interview",
) -> str:
    """Generate a beautiful HTML email from summary and transcript."""
    summary_html = format_summary_html(summary_text)
    transcript_html = format_transcript_html(transcript_text)

    if not interview_type or interview_type == "Unknown":
        interview_type = "Session"
    if not candidate_name:
        candidate_name = "Unknown"

    escaped_interview_type = html.escape(str(interview_type))
    escaped_candidate_name = html.escape(str(candidate_name))

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


async def send_test_email():
    """Send test email."""
    load_dotenv()

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("❌ RESEND_API_KEY environment variable is not set")
        return False

    email_domain = os.getenv("RESEND_EMAIL_DOMAIN")
    if not email_domain:
        print("❌ RESEND_EMAIL_DOMAIN environment variable is not set")
        return False

    resend.api_key = api_key
    from_email = f"PailFlow <noreply@{email_domain}>"
    to_email = "work@lunchpaillabs.com"

    # Test data with JSON summary (like lead qualification)
    test_summary_json = {
        "call_name": "Lead Qualification Call",
        "lead": {
            "name": "John Smith",  # This should show in the email
            "problem": "I want to bake a cake for my daughter's birthday party this weekend.",
            "current_workaround": "I've tried following recipes online but they keep turning out wrong.",
            "timeline": "This weekend (urgent)",
            "budget": "$50-100",
            "decision_maker": "Just me",
            "quick_fit_score": 7.5,
        },
        "recommendation": "Schedule a discovery call to learn more about our baking solutions.",
    }

    test_summary = json.dumps(test_summary_json, indent=2)

    test_transcript = """[2025-12-01T10:00:00.000+00:00] assistant: Hi! I'm going to ask you a few quick questions to see how we can help. This will only take a couple of minutes.

[2025-12-01T10:00:05.000+00:00] user: Yeah. That sounds great, actually.

[2025-12-01T10:00:10.000+00:00] assistant: What problem are you trying to solve?

[2025-12-01T10:00:15.000+00:00] user: I want to bake a cake for my daughter's birthday party this weekend. I've never been great at baking and I want it to turn out perfect.

[2025-12-01T10:00:25.000+00:00] assistant: I see, so you need to figure out how to bake a cake by today. Can you tell me more about what challenges you're facing with that?

[2025-12-01T10:00:30.000+00:00] user: I've tried following recipes online but they keep turning out wrong. The cakes are either too dry or don't rise properly.

[2025-12-01T10:00:40.000+00:00] assistant: What have you tried so far to solve this?

[2025-12-01T10:00:45.000+00:00] user: I've tried following recipes online but they keep turning out wrong. The cakes are either too dry or don't rise properly.

[2025-12-01T10:00:55.000+00:00] assistant: How soon do you need this solved?

[2025-12-01T10:01:00.000+00:00] user: This weekend - her birthday is on Saturday, so I need to have it ready by then.

[2025-12-01T10:01:10.000+00:00] assistant: What's your budget range for solving this?

[2025-12-01T10:01:15.000+00:00] user: I'm willing to spend around $50-100 to make sure it turns out well.

[2025-12-01T10:01:25.000+00:00] assistant: Who is involved in the decision-making process?

[2025-12-01T10:01:30.000+00:00] user: Just me - I'm the one making the cake, so it's my decision.

[2025-12-01T10:01:40.000+00:00] assistant: Perfect! I have everything I need. I'll send you a summary via email shortly. Thanks for your time!

[2025-12-01T10:01:45.000+00:00] user: Thanks for the call. Talk later. Bye bye."""

    html_body = generate_html_email(
        summary_text=test_summary,
        transcript_text=test_transcript,
        candidate_name="John Smith",
        interview_type="Lead Qualification Call",
    )

    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [to_email],
        "subject": "Qualification Complete: John Smith",
        "html": html_body,
        "reply_to": f"noreply@{email_domain}",
    }

    print(f"\n{'='*80}")
    print("📧 Sending test email...")
    print(f"{'='*80}\n")
    print(f"To: {to_email}")
    print("Subject: Qualification Complete: John Smith")
    print("Interview Type: Lead Qualification Call")
    print("Candidate Name: John Smith")
    print()

    try:
        email = resend.Emails.send(params)
        print("✅ Email sent successfully!")
        print(f"   Email ID: {email.get('id', 'N/A')}")
        print(f"\n{'='*80}\n")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        print(f"\n{'='*80}\n")
        return False


if __name__ == "__main__":
    asyncio.run(send_test_email())
