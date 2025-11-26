#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Script to configure Daily.co webhooks via API.

**Simple Explanation:**
This script creates a webhook in Daily.co that sends events to your
Cloudflare Worker. Daily.co will send webhooks when recordings and
transcripts are ready to download.

Usage:
    python scripts/setup_daily_webhooks.py
    # Or with custom values:
    DAILY_API_KEY=your-key WEBHOOK_URL=https://your-worker.workers.dev python scripts/setup_daily_webhooks.py
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load .env from project root or subdirectories
    env_paths = [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent / "flow" / ".env",
        Path(__file__).parent.parent / "api" / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass


def get_daily_headers(api_key: str) -> Dict[str, str]:
    """
    Get HTTP headers for Daily.co API requests.

    **Simple Explanation:**
    Formats the API key as a Bearer token for authentication.
    """
    auth_header = api_key.strip()
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }


def list_webhooks(api_key: str) -> List[Dict[str, Any]]:
    """
    List all existing webhooks in Daily.co.

    **Simple Explanation:**
    Calls Daily.co's API to get a list of all webhooks you've configured.
    This helps us see if a webhook already exists before creating a new one.
    """
    headers = get_daily_headers(api_key)

    try:
        async def fetch():
            async with httpx.AsyncClient() as client:
                endpoint = "https://api.daily.co/v1/webhooks"
                response = await client.get(
                    endpoint,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                # Daily.co returns webhooks in a 'data' array, or sometimes directly as a list
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("data", [])
                else:
                    return []

        import asyncio
        return asyncio.run(fetch())

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", str(e))
            print(f"❌ Daily.co API error: {error_detail} (status: {e.response.status_code})")
        except Exception:
            print(f"❌ Daily.co API error: {e}")
        return []
    except Exception as e:
        print(f"❌ Failed to list webhooks: {e}")
        return []


def create_webhook(
    api_key: str,
    webhook_url: str,
    event_types: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Create a new webhook in Daily.co.

    **Simple Explanation:**
    This creates a webhook that tells Daily.co to send events to your
    Cloudflare Worker URL. When a recording or transcript is ready,
    Daily.co will POST a webhook to your worker.

    Args:
        api_key: Daily.co API key
        webhook_url: URL of your Cloudflare Worker (where webhooks should be sent)
        event_types: List of event types to subscribe to (e.g., ["recording.ready-to-download"])

    Returns:
        The created webhook data, or None if creation failed
    """
    headers = get_daily_headers(api_key)

    payload = {
        "url": webhook_url,
        "eventTypes": event_types,
    }

    try:
        async def create():
            async with httpx.AsyncClient() as client:
                endpoint = "https://api.daily.co/v1/webhooks"
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

        import asyncio
        return asyncio.run(create())

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", str(e))
            print(f"❌ Daily.co API error: {error_detail} (status: {e.response.status_code})")

            # Provide helpful error messages
            if e.response.status_code == 400:
                print("\n💡 This usually means:")
                print("   - The webhook URL didn't return 200 OK to Daily.co's test request")
                print("   - Make sure your worker is deployed and responding correctly")
                print("   - Check worker logs: wrangler tail")
        except Exception:
            print(f"❌ Daily.co API error: {e}")
        return None
    except Exception as e:
        print(f"❌ Failed to create webhook: {e}")
        return None


def update_webhook(
    api_key: str,
    webhook_id: str,
    webhook_url: str,
    event_types: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Update an existing webhook in Daily.co.

    **Simple Explanation:**
    Updates a webhook that already exists. This is useful if you need to
    change the URL or event types.
    """
    headers = get_daily_headers(api_key)

    payload = {
        "url": webhook_url,
        "eventTypes": event_types,
    }

    try:
        async def update():
            async with httpx.AsyncClient() as client:
                endpoint = f"https://api.daily.co/v1/webhooks/{webhook_id}"
                response = await client.put(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

        import asyncio
        return asyncio.run(update())

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", str(e))
            print(f"❌ Daily.co API error: {error_detail} (status: {e.response.status_code})")
        except Exception:
            print(f"❌ Daily.co API error: {e}")
        return None
    except Exception as e:
        print(f"❌ Failed to update webhook: {e}")
        return None


def delete_webhook(api_key: str, webhook_id: str) -> bool:
    """
    Delete a webhook from Daily.co.

    **Simple Explanation:**
    Removes a webhook so Daily.co stops sending events to that URL.
    """
    headers = get_daily_headers(api_key)

    try:
        async def delete():
            async with httpx.AsyncClient() as client:
                endpoint = f"https://api.daily.co/v1/webhooks/{webhook_id}"
                response = await client.delete(
                    endpoint,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return True

        import asyncio
        return asyncio.run(delete())

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", str(e))
            print(f"❌ Daily.co API error: {error_detail} (status: {e.response.status_code})")
        except Exception:
            print(f"❌ Daily.co API error: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to delete webhook: {e}")
        return False


def main():
    """Main function to set up Daily.co webhooks."""
    # Get API key from environment variable
    api_key = os.getenv("DAILY_API_KEY")
    if not api_key:
        print("❌ Error: DAILY_API_KEY environment variable not set")
        print("\nUsage:")
        print("  DAILY_API_KEY=your-key python scripts/setup_daily_webhooks.py")
        print("\nOr set it in your .env file:")
        print("  export DAILY_API_KEY=your-key")
        print("  python scripts/setup_daily_webhooks.py")
        sys.exit(1)

    # Get webhook URL from environment variable or prompt
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        print("📋 Webhook URL not set in environment")
        print("   Enter your Cloudflare Worker URL (e.g., https://pailkit-webhook-router.your-subdomain.workers.dev)")
        webhook_url = input("   Webhook URL: ").strip()

        if not webhook_url:
            print("❌ Error: Webhook URL is required")
            sys.exit(1)

        # Validate URL format
        if not webhook_url.startswith("http://") and not webhook_url.startswith("https://"):
            print("❌ Error: Webhook URL must start with http:// or https://")
            sys.exit(1)

    # Event types we want to subscribe to
    event_types = [
        "transcript.ready-to-download",
        "recording.ready-to-download",
    ]

    print("🔗 Setting up Daily.co webhooks...")
    print(f"   Webhook URL: {webhook_url}")
    print(f"   Event types: {', '.join(event_types)}")
    print()

    # Check for existing webhooks
    print("🔍 Checking for existing webhooks...")
    existing_webhooks = list_webhooks(api_key)

    # Look for webhooks pointing to our URL
    matching_webhook = None
    for webhook in existing_webhooks:
        if webhook.get("url") == webhook_url:
            matching_webhook = webhook
            break

    if matching_webhook:
        # Daily.co uses "uuid" as the ID field
        webhook_id = matching_webhook.get("uuid") or matching_webhook.get("id")
        existing_events = matching_webhook.get("eventTypes", [])

        print(f"✅ Found existing webhook (ID: {webhook_id})")
        print(f"   Current events: {', '.join(existing_events)}")
        print()

        # Check if we need to update
        if set(existing_events) == set(event_types):
            print("✅ Webhook is already configured correctly!")
            print("   No changes needed.")
            return

        # Ask if user wants to update
        print("⚠️  Webhook exists but has different event types")
        response = input("   Update webhook? (y/n): ").strip().lower()

        if response == "y":
            print("🔄 Updating webhook...")
            result = update_webhook(api_key, webhook_id, webhook_url, event_types)
            if result:
                print("✅ Webhook updated successfully!")
                webhook_result_id = result.get('uuid') or result.get('id', webhook_id)
                print(f"   Webhook ID: {webhook_result_id}")
                print(f"   Events: {', '.join(event_types)}")
            else:
                print("❌ Failed to update webhook")
                sys.exit(1)
        else:
            print("ℹ️  Keeping existing webhook configuration")
    else:
        # Create new webhook
        print("📝 Creating new webhook...")
        print()
        print("💡 Note: Daily.co will send a test request to verify your endpoint")
        print("   Make sure your worker is deployed and returns 200 OK")
        print()

        result = create_webhook(api_key, webhook_url, event_types)
        if result:
            # Daily.co uses "uuid" as the ID field
            webhook_id = result.get("uuid") or result.get("id", "unknown")
            print("✅ Webhook created successfully!")
            print(f"   Webhook ID: {webhook_id}")
            print(f"   URL: {webhook_url}")
            print(f"   Events: {', '.join(event_types)}")
            print()
            print("🎉 Your webhook is now active!")
            print("   Daily.co will send webhooks when recordings and transcripts are ready.")
        else:
            print("❌ Failed to create webhook")
            print()
            print("💡 Troubleshooting:")
            print("   1. Make sure your worker is deployed: cd workers && ./deploy.sh")
            print("   2. Check that the webhook URL is correct")
            print("   3. Verify your worker returns 200 OK: wrangler tail")
            print("   4. Check Daily.co API key permissions")
            sys.exit(1)


if __name__ == "__main__":
    main()
