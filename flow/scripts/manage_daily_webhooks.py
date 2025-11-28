#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Manage Daily.co Webhooks

This script helps you set up and manage Daily.co webhooks for your application.
It supports:
- Listing existing webhooks
- Creating new webhooks
- Updating existing webhooks
- Deleting webhooks

**Simple Explanation:**
Daily.co sends webhooks (HTTP POST requests) to your server when events happen
(like when a meeting ends, a transcript is ready, or a recording is ready).
This script helps you configure which events Daily.co should send to your server.

Usage:
    # List all webhooks
    python scripts/manage_daily_webhooks.py list

    # Create a new webhook
    python scripts/manage_daily_webhooks.py create --url https://your-app.com/webhooks

    # Update an existing webhook (add meeting.ended event)
    python scripts/manage_daily_webhooks.py update --webhook-id <webhook-id> --add-event meeting.ended

    # Delete a webhook
    python scripts/manage_daily_webhooks.py delete --webhook-id <webhook-id>
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv

    # Load .env from flow/ directory or parent directory
    env_paths = [
        Path(__file__).parent.parent / ".env",  # flow/.env
        Path(__file__).parent.parent.parent / ".env",  # project root .env
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass


def get_daily_api_key() -> str:
    """Get Daily.co API key from environment variable."""
    api_key = os.getenv("DAILY_API_KEY")
    if not api_key:
        print("❌ Error: DAILY_API_KEY environment variable is not set")
        print("   Set it in your .env file or export it:")
        print("   export DAILY_API_KEY=your-api-key-here")
        print("\n   Or create a .env file in the flow/ directory with:")
        print("   DAILY_API_KEY=your-api-key-here")
        sys.exit(1)
    return api_key.strip()


def get_daily_headers() -> Dict[str, str]:
    """Get HTTP headers for Daily.co API requests."""
    api_key = get_daily_api_key()
    auth_header = api_key
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }


def list_webhooks() -> List[Dict[str, Any]]:
    """List all Daily.co webhooks."""
    headers = get_daily_headers()

    try:
        with httpx.Client() as client:
            response = client.get("https://api.daily.co/v1/webhooks", headers=headers)
            response.raise_for_status()
            result = response.json()
            # Daily.co API returns either a list directly or {"data": [...]}
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "data" in result:
                return result["data"]
            else:
                return []
    except httpx.HTTPStatusError as e:
        print(f"❌ Error listing webhooks: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def create_webhook(url: str, event_types: List[str]) -> Dict[str, Any]:
    """Create a new Daily.co webhook."""
    headers = get_daily_headers()

    payload = {
        "url": url,
        "eventTypes": event_types,
    }

    try:
        with httpx.Client() as client:
            response = client.post(
                "https://api.daily.co/v1/webhooks", headers=headers, json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        print(f"❌ Error creating webhook: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def update_webhook(
    webhook_id: str, url: str = None, event_types: List[str] = None
) -> Dict[str, Any]:
    """Update an existing Daily.co webhook."""
    headers = get_daily_headers()

    # First, get the current webhook to merge with existing event types
    try:
        with httpx.Client() as client:
            get_response = client.get(
                f"https://api.daily.co/v1/webhooks/{webhook_id}", headers=headers
            )
            get_response.raise_for_status()
            current_webhook = get_response.json()
    except httpx.HTTPStatusError as e:
        print(f"❌ Error getting webhook: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)

    # Merge event types
    current_event_types = current_webhook.get("eventTypes", [])
    if event_types:
        # Combine and deduplicate
        all_event_types = list(set(current_event_types + event_types))
    else:
        all_event_types = current_event_types

    # Use provided URL or keep existing
    webhook_url = url or current_webhook.get("url")

    payload = {
        "url": webhook_url,
        "eventTypes": all_event_types,
    }

    try:
        with httpx.Client() as client:
            response = client.post(
                f"https://api.daily.co/v1/webhooks/{webhook_id}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        print(f"❌ Error updating webhook: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def delete_webhook(webhook_id: str) -> None:
    """Delete a Daily.co webhook."""
    headers = get_daily_headers()

    try:
        with httpx.Client() as client:
            response = client.delete(
                f"https://api.daily.co/v1/webhooks/{webhook_id}", headers=headers
            )
            response.raise_for_status()
            print(f"✅ Webhook {webhook_id} deleted successfully")
    except httpx.HTTPStatusError as e:
        print(f"❌ Error deleting webhook: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Manage Daily.co webhooks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all webhooks
  python scripts/manage_daily_webhooks.py list

  # Create a new webhook with all required events
  python scripts/manage_daily_webhooks.py create \\
    --url https://your-app.com/webhooks \\
    --events meeting.ended transcript.ready-to-download recording.ready-to-download

  # Update existing webhook to add meeting.ended event
  python scripts/manage_daily_webhooks.py update \\
    --webhook-id abc123 \\
    --add-event meeting.ended

  # Delete a webhook
  python scripts/manage_daily_webhooks.py delete --webhook-id abc123
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all webhooks")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new webhook")
    create_parser.add_argument(
        "--url", required=True, help="Webhook URL (e.g., https://your-app.com/webhooks)"
    )
    create_parser.add_argument(
        "--events",
        nargs="+",
        default=[
            "meeting.ended",
            "transcript.ready-to-download",
            "recording.ready-to-download",
        ],
        help="Event types to subscribe to (default: meeting.ended transcript.ready-to-download recording.ready-to-download)",
    )

    # Update command
    update_parser = subparsers.add_parser("update", help="Update an existing webhook")
    update_parser.add_argument(
        "--webhook-id", required=True, help="Webhook ID to update"
    )
    update_parser.add_argument("--url", help="New webhook URL (optional)")
    update_parser.add_argument(
        "--add-event",
        action="append",
        dest="add_events",
        help="Add event type (can be used multiple times)",
    )
    update_parser.add_argument(
        "--events",
        nargs="+",
        help="Replace all event types with these (overrides --add-event)",
    )

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a webhook")
    delete_parser.add_argument(
        "--webhook-id", required=True, help="Webhook ID to delete"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        print("📋 Listing Daily.co webhooks...\n")
        webhooks = list_webhooks()

        if not webhooks:
            print("   No webhooks found")
        else:
            for webhook in webhooks:
                # Try different possible ID field names (Daily.co uses "uuid")
                webhook_id = (
                    webhook.get("id")
                    or webhook.get("uuid")
                    or webhook.get("webhook_id")
                    or webhook.get("_id")
                    or "N/A"
                )
                url = webhook.get("url", "N/A")
                event_types = webhook.get("eventTypes", webhook.get("event_types", []))
                print(f"🔗 Webhook ID: {webhook_id}")
                print(f"   URL: {url}")
                print(f"   Events: {', '.join(event_types)}")
                if webhook_id == "N/A":
                    print("   ⚠️  Note: Could not find webhook ID in response")
                    print("   Full webhook data:", json.dumps(webhook, indent=2))
                print()

    elif args.command == "create":
        print(f"➕ Creating webhook for URL: {args.url}")
        print(f"   Events: {', '.join(args.events)}\n")
        result = create_webhook(args.url, args.events)
        webhook_id = result.get("id", "N/A")
        print("✅ Webhook created successfully!")
        print(f"   Webhook ID: {webhook_id}")
        print(f"   URL: {result.get('url')}")
        print(f"   Events: {', '.join(result.get('eventTypes', []))}")

    elif args.command == "update":
        events_to_use = None
        if args.events:
            events_to_use = args.events
        elif args.add_events:
            events_to_use = args.add_events

        print(f"🔄 Updating webhook: {args.webhook_id}")
        if args.url:
            print(f"   New URL: {args.url}")
        if events_to_use:
            print(f"   Events: {', '.join(events_to_use)}")
        print()

        result = update_webhook(
            args.webhook_id, url=args.url, event_types=events_to_use
        )
        print("✅ Webhook updated successfully!")
        print(f"   Webhook ID: {result.get('id')}")
        print(f"   URL: {result.get('url')}")
        print(f"   Events: {', '.join(result.get('eventTypes', []))}")

    elif args.command == "delete":
        print(f"🗑️  Deleting webhook: {args.webhook_id}\n")
        delete_webhook(args.webhook_id)


if __name__ == "__main__":
    main()
