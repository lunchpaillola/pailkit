#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Script to delete all Daily.co webhooks.

**Simple Explanation:**
This script lists all your webhooks and deletes them. This is useful
when you need to start fresh after a webhook configuration fails.

Usage:
    python scripts/delete_daily_webhooks.py
    # Or with custom API key:
    DAILY_API_KEY=your-key python scripts/delete_daily_webhooks.py
"""

import argparse
import os
import sys
from pathlib import Path

# Import functions from setup_daily_webhooks.py
sys.path.insert(0, str(Path(__file__).parent))
from setup_daily_webhooks import list_webhooks, delete_webhook, get_daily_headers

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


def main():
    """Main function to delete all Daily.co webhooks."""
    # Get API key from environment variable
    api_key = os.getenv("DAILY_API_KEY")
    if not api_key:
        print("❌ Error: DAILY_API_KEY environment variable not set")
        print("\nUsage:")
        print("  DAILY_API_KEY=your-key python scripts/delete_daily_webhooks.py")
        print("\nOr set it in your .env file:")
        print("  export DAILY_API_KEY=your-key")
        print("  python scripts/delete_daily_webhooks.py")
        sys.exit(1)

    print("🔍 Listing all existing webhooks...")
    existing_webhooks = list_webhooks(api_key)

    if not existing_webhooks:
        print("✅ No webhooks found. Nothing to delete!")
        return

    print(f"\n📋 Found {len(existing_webhooks)} webhook(s):")
    for i, webhook in enumerate(existing_webhooks, 1):
        # Try different possible ID field names (Daily.co uses "uuid")
        webhook_id = webhook.get("uuid") or webhook.get("id") or webhook.get("webhook_id") or webhook.get("_id")
        webhook_url = webhook.get("url", "unknown")
        events = webhook.get("eventTypes", [])
        print(f"   {i}. ID: {webhook_id or 'unknown'}")
        print(f"      URL: {webhook_url}")
        print(f"      Events: {', '.join(events)}")
        if not webhook_id:
            # Debug: print the full webhook structure
            print(f"      Debug - Full webhook data: {webhook}")
        print()

    # Auto-confirm deletion (non-interactive mode)
    print("⚠️  Deleting ALL webhooks listed above...")

    # Delete all webhooks
    print("\n🗑️  Deleting webhooks...")
    deleted_count = 0
    failed_count = 0

    for webhook in existing_webhooks:
        # Try different possible ID field names (Daily.co uses "uuid")
        webhook_id = webhook.get("uuid") or webhook.get("id") or webhook.get("webhook_id") or webhook.get("_id")
        webhook_url = webhook.get("url", "unknown")

        if not webhook_id:
            print(f"⚠️  Skipping webhook with no ID: {webhook_url}")
            print(f"   Full webhook data: {webhook}")
            continue

        print(f"   Deleting webhook {webhook_id} ({webhook_url})...")
        if delete_webhook(api_key, webhook_id):
            print(f"   ✅ Deleted webhook {webhook_id}")
            deleted_count += 1
        else:
            print(f"   ❌ Failed to delete webhook {webhook_id}")
            failed_count += 1

    print(f"\n✅ Deletion complete!")
    print(f"   Deleted: {deleted_count}")
    if failed_count > 0:
        print(f"   Failed: {failed_count}")


if __name__ == "__main__":
    main()
