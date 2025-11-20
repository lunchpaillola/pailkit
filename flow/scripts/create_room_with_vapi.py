#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Create a room with VAPI enabled for manual testing.

This script creates a real room, enables PIN dial-in, and creates a VAPI call.
It prints all the information you need to join the call and waits so you can join.
It also updates the static values in test_vapi_static_dial.py.

Run with: python flow/scripts/create_room_with_vapi.py

Note: This requires valid API keys in your .env file:
- DAILY_API_KEY
- VAPI_API_KEY
- VAPI_ASSISTANT_ID
- VAPI_PHONE_NUMBER_ID
- DAILY_PHONE_NUMBER (Daily.co phone number for dial-in)

The VAPI assistant must be configured to use the "dial-keypad-dtmf" tool
(https://docs.vapi.ai/tools/default-tools#dial-keypad-dtmf) to dial the PIN
after connecting to the phone number.
"""

import asyncio
import os
import re
import sys
from dotenv import load_dotenv

# Add project root to path so we can import flow modules
# This script is in flow/scripts/, so we need to go up two levels to get to project root
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)  # flow/
project_root = os.path.dirname(flow_dir)  # project root (pailkit/)
sys.path.insert(0, project_root)

from flow.workflows.one_time_meeting import OneTimeMeetingWorkflow  # noqa: E402


def update_static_values(phone: str, pin: str):
    """Update static values in test_vapi_static_dial.py."""
    # Path to the test script
    test_script_path = os.path.join(flow_dir, "scripts", "test_vapi_static_dial.py")

    if not os.path.exists(test_script_path):
        print(f"⚠️  Warning: {test_script_path} not found, skipping update")
        return

    # Read the file
    with open(test_script_path, "r") as f:
        content = f.read()

    # Update STATIC_PHONE
    content = re.sub(
        r'STATIC_PHONE = "[^"]*"',
        f'STATIC_PHONE = "{phone}"',
        content,
    )

    # Update STATIC_PIN (make sure it includes #)
    pin_with_pound = pin if pin.endswith("#") else f"{pin}#"
    content = re.sub(
        r'STATIC_PIN = "[^"]*"',
        f'STATIC_PIN = "{pin_with_pound}"',
        content,
    )

    # Write back
    with open(test_script_path, "w") as f:
        f.write(content)

    print(f"\n{'='*80}")
    print("📝 Updated static values in test_vapi_static_dial.py:")
    print(f"   STATIC_PHONE = {phone}")
    print(f"   STATIC_PIN = {pin_with_pound}")
    print(f"{'='*80}\n")


async def main():
    """Create room with VAPI and wait for user to join."""
    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")
    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")
    vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

    if not all([daily_api_key, vapi_api_key, vapi_assistant_id, vapi_phone_number_id]):
        missing = []
        if not daily_api_key:
            missing.append("DAILY_API_KEY")
        if not vapi_api_key:
            missing.append("VAPI_API_KEY")
        if not vapi_assistant_id:
            missing.append("VAPI_ASSISTANT_ID")
        if not vapi_phone_number_id:
            missing.append("VAPI_PHONE_NUMBER_ID")
        print(
            f"❌ Missing required API keys in environment variables: {', '.join(missing)}"
        )
        sys.exit(1)

    workflow = OneTimeMeetingWorkflow()

    context = {
        "meeting_config": {
            "autoRecord": True,
            "autoTranscribe": True,
            "vapi": {
                "enabled": True,
                "assistant_id": vapi_assistant_id,
            },
        },
        "provider_keys": {
            "room_provider_key": daily_api_key,
            "vapi_api_key": vapi_api_key,
        },
    }

    # Set the base URL for the hosted meeting page
    os.environ["MEET_BASE_URL"] = os.getenv("MEET_BASE_URL", "http://localhost:8001")

    print(f"\n{'='*80}")
    print("🚀 Creating room with VAPI calling enabled...")
    print(f"{'='*80}\n")

    result = await workflow.execute_async(context)

    # Get room info from result
    room_name = result.get("room_name")
    room_url = result.get("room_url")
    hosted_url = result.get("hosted_url")
    dialin_code = result.get("dialin_code")
    vapi_call_created = result.get("vapi_call_created", False)
    vapi_call_id = result.get("vapi_call_id")
    vapi_call_error = result.get("vapi_call_error")

    print(f"\n{'='*80}")
    print("✅ ROOM CREATED SUCCESSFULLY!")
    print(f"{'='*80}\n")

    if room_name:
        print("📋 Room Details:")
        print(f"   Room Name: {room_name}")
        print(f"   Room URL: {room_url}\n")

        if dialin_code:
            daily_phone_number = os.getenv(
                "DAILY_PHONE_NUMBER", "your-daily-phone-number"
            )
            print("📱 PIN Dial-in Information:")
            print(f"   PIN Code: {dialin_code}")
            print(f"   PIN with #: {dialin_code}#")
            print(f"   Phone Number: {daily_phone_number}")
            print(
                f"   VAPI will dial {daily_phone_number} and enter PIN {dialin_code}# via DTMF\n"
            )

            # Update static values in test_vapi_static_dial.py
            if daily_phone_number != "your-daily-phone-number":
                update_static_values(daily_phone_number, dialin_code)

        print(f"{'='*80}")
        print("🔗 JOIN THE MEETING - Use this link:")
        print(f"   {room_url}")
        print(f"{'='*80}\n")

        if hosted_url and hosted_url.startswith("http://localhost"):
            print("💡 NOTE: For the hosted meeting page (with custom branding),")
            print("   start the server first:")
            print("   cd flow && python main.py")
            print(f"   Then visit: {hosted_url}\n")

        if dialin_code:
            daily_phone_number = os.getenv(
                "DAILY_PHONE_NUMBER", "your-daily-phone-number"
            )
            print("📞 VAPI will dial phone number and enter PIN:")
            print(f"   Phone: {daily_phone_number}")
            print(f"   PIN: {dialin_code}# (via DTMF - note the # key at the end)\n")

        print(f"{'='*80}")
        print("🤖 VAPI Call Status:")
        print(f"{'='*80}")
        if vapi_call_created:
            print("   ✅ VAPI call created successfully!")
            if vapi_call_id:
                print(f"   Call ID: {vapi_call_id}")
            daily_phone_number = os.getenv(
                "DAILY_PHONE_NUMBER", "your-daily-phone-number"
            )
            print(
                f"\n   VAPI is dialing {daily_phone_number} and will enter PIN {dialin_code}# via DTMF"
            )
            print("   ⏳ Waiting for VAPI to connect and join the room...")
            print("   (This usually takes 5-15 seconds)\n")

            # Wait for VAPI to connect (give it time to dial and join)
            # **Simple Explanation:** VAPI needs time to:
            # 1. Process the call request
            # 2. Dial the Daily.co phone number
            # 3. Enter the PIN via DTMF
            # 4. Connect to Daily.co and join the room
            # We wait a bit to give it time to complete this process
            wait_seconds = 15
            for i in range(wait_seconds):
                await asyncio.sleep(1)
                remaining = wait_seconds - i - 1
                if remaining > 0 and remaining % 3 == 0:  # Print every 3 seconds
                    print(f"   ⏳ Still waiting... ({remaining} seconds remaining)")

            print("\n   ✅ VAPI should have joined by now!")
            print("   You can now join via the link above to test!")
        elif vapi_call_error:
            print(f"   ⚠️ VAPI call failed: {vapi_call_error}")
            print("   Room is still available - you can join manually")
        else:
            print("   ⚠️ VAPI call status unknown")
        print(f"{'='*80}\n")

        print("💡 TIP: Open the meeting link in your browser to join as a participant")
        print("   VAPI should already be in the room via phone dial-in\n")

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

    # Verify room was created
    assert room_name is not None, f"Room should be created. Result: {result}"
    assert room_url is not None, f"Room URL should be available. Result: {result}"

    # If VAPI is enabled, we should have dialin_code info
    assert (
        dialin_code is not None
    ), "dialin_code should be available when VAPI is enabled"


if __name__ == "__main__":
    asyncio.run(main())
