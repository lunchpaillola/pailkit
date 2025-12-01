#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Test script to check Daily.co room status.

This script checks:
1. Daily.co room details
2. Room participants (if available)

Usage:
    python flow/scripts/test_room_status.py <room_name>

Example:
    python flow/scripts/test_room_status.py g6c2GYUhQojQ69UiqG8b
"""

import asyncio
import json
import os
import sys
from dotenv import load_dotenv

import httpx


async def check_daily_room(room_name: str, api_key: str):
    """Check Daily.co room details."""
    print(f"\n{'='*80}")
    print(f"📹 Checking Daily.co Room: {room_name}")
    print(f"{'='*80}\n")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with httpx.AsyncClient() as client:
            # Get room details
            response = await client.get(
                f"https://api.daily.co/v1/rooms/{room_name}",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            room_data = response.json()

            print("✅ Room Details:")
            print(f"   Room Name: {room_data.get('name')}")
            print(f"   Room URL: {room_data.get('url')}")
            print(f"   Privacy: {room_data.get('privacy')}")
            print(f"   Created: {room_data.get('created_at')}")

            config = room_data.get("config", {})
            if config:
                print("\n   Config:")
                print(f"   - SIP enabled: {bool(config.get('sip'))}")
                sip_config = config.get("sip", {})
                if sip_config:
                    print(f"   - SIP mode: {sip_config.get('sip_mode')}")
                    print(f"   - Display name: {sip_config.get('display_name')}")

                sip_uri = config.get("sip_uri", {})
                if sip_uri:
                    print(f"   - SIP URI endpoint: {sip_uri.get('endpoint')}")

            # Try to get meeting info (for active participants)
            # Daily.co REST API doesn't have a direct participants endpoint
            # But we can check if there's meeting data
            print("\n   Note: Daily.co REST API doesn't provide active participants.")
            print("   Participants are only available via Daily.co's client SDK.")

            return room_data

    except httpx.HTTPStatusError as e:
        print(f"❌ Error checking room: {e.response.status_code}")
        try:
            error_data = e.response.json()
            print(f"   Error: {json.dumps(error_data, indent=2)}")
        except (json.JSONDecodeError, ValueError):
            print(f"   Error: {e.response.text}")
        return None
    except Exception as e:
        print(f"❌ Failed to check room: {str(e)}")
        return None


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python flow/scripts/test_room_status.py <room_name>")
        print("\nExample:")
        print("  python flow/scripts/test_room_status.py g6c2GYUhQojQ69UiqG8b")
        sys.exit(1)

    load_dotenv()

    room_name = sys.argv[1]

    daily_api_key = os.getenv("DAILY_API_KEY")

    if not daily_api_key:
        print("❌ Missing DAILY_API_KEY in environment")
        sys.exit(1)

    # Check Daily.co room
    await check_daily_room(room_name, daily_api_key)

    print(f"\n{'='*80}")
    print("✅ Diagnostics complete!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
