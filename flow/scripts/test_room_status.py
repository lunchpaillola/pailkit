#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Test script to check room status and VAPI call status.

This script checks:
1. Daily.co room details
2. VAPI call status
3. Room participants (if available)

Usage:
    python flow/scripts/test_room_status.py <room_name> [vapi_call_id]

Example:
    python flow/scripts/test_room_status.py g6c2GYUhQojQ69UiqG8b 019a9299-96f7-7770-a5c7-c5bcc38a4fea
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


async def check_vapi_call(call_id: str, api_key: str):
    """Check VAPI call status."""
    print(f"\n{'='*80}")
    print(f"📞 Checking VAPI Call: {call_id}")
    print(f"{'='*80}\n")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with httpx.AsyncClient() as client:
            # Get call details
            response = await client.get(
                f"https://api.vapi.ai/call/{call_id}",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            call_data = response.json()

            print("✅ VAPI Call Status:")
            print(f"   Call ID: {call_data.get('id')}")
            print(f"   Status: {call_data.get('status')}")
            print(f"   Created: {call_data.get('createdAt')}")
            print(f"   Updated: {call_data.get('updatedAt')}")

            # Check customer info
            customer = call_data.get("customer", {})
            if customer:
                print("\n   Customer:")
                print(f"   - Number: {customer.get('number')}")
                print(f"   - SIP URI: {customer.get('sipUri')}")
                print(f"   - Name: {customer.get('name')}")

            # Check assistant
            assistant = call_data.get("assistant", {})
            if assistant:
                print("\n   Assistant:")
                print(f"   - ID: {assistant.get('id')}")
                print(f"   - Name: {assistant.get('name')}")

            # Check phone number
            phone_number = call_data.get("phoneNumber", {})
            if phone_number:
                print("\n   Phone Number:")
                print(f"   - ID: {phone_number.get('id')}")
                print(f"   - Number: {phone_number.get('number')}")

            # Check for any errors or messages
            messages = call_data.get("messages", [])
            if messages:
                print(f"\n   Messages ({len(messages)}):")
                for msg in messages[-5:]:  # Show last 5 messages
                    print(f"   - {msg.get('type')}: {msg.get('content', '')[:100]}")

            # Check for end reason
            end_reason = call_data.get("endReason")
            if end_reason:
                print(f"\n   End Reason: {end_reason}")

            return call_data

    except httpx.HTTPStatusError as e:
        print(f"❌ Error checking VAPI call: {e.response.status_code}")
        try:
            error_data = e.response.json()
            print(f"   Error: {json.dumps(error_data, indent=2)}")
        except (json.JSONDecodeError, ValueError):
            print(f"   Error: {e.response.text}")
        return None
    except Exception as e:
        print(f"❌ Failed to check VAPI call: {str(e)}")
        return None


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print(
            "Usage: python flow/scripts/test_room_status.py <room_name> [vapi_call_id]"
        )
        print("\nExample:")
        print(
            "  python flow/scripts/test_room_status.py g6c2GYUhQojQ69UiqG8b 019a9299-96f7-7770-a5c7-c5bcc38a4fea"
        )
        sys.exit(1)

    load_dotenv()

    room_name = sys.argv[1]
    vapi_call_id = sys.argv[2] if len(sys.argv) > 2 else None

    daily_api_key = os.getenv("DAILY_API_KEY")
    vapi_api_key = os.getenv("VAPI_API_KEY")

    if not daily_api_key:
        print("❌ Missing DAILY_API_KEY in environment")
        sys.exit(1)

    # Check Daily.co room
    await check_daily_room(room_name, daily_api_key)

    # Check VAPI call if call ID provided
    if vapi_call_id:
        if not vapi_api_key:
            print("\n⚠️  Missing VAPI_API_KEY in environment - skipping VAPI call check")
        else:
            await check_vapi_call(vapi_call_id, vapi_api_key)
    else:
        print("\n💡 Tip: Provide VAPI call ID as second argument to check call status")
        print(
            f"   Example: python flow/scripts/test_room_status.py {room_name} <call_id>"
        )

    print(f"\n{'='*80}")
    print("✅ Diagnostics complete!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
