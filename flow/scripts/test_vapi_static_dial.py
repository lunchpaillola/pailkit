#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Test VAPI with static phone number and PIN.

This script makes a VAPI call with static phone/PIN values.
No room creation - just dials the number.

Run with: python flow/scripts/test_vapi_static_dial.py

Note: This requires valid API keys in your .env file:
- VAPI_API_KEY
- VAPI_ASSISTANT_ID
- VAPI_PHONE_NUMBER_ID
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path so we can import flow modules
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)  # flow/
project_root = os.path.dirname(flow_dir)  # project root (pailkit/)
sys.path.insert(0, project_root)

import httpx  # noqa: E402

# Static values for testing
STATIC_PHONE = "12092080701"
STATIC_PIN = "16774140126#"


def _get_vapi_headers(api_key: str) -> dict[str, str]:
    """Get HTTP headers for VAPI API requests."""
    auth_header = api_key.strip()
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }


async def get_assistant_config(api_key: str, assistant_id: str) -> dict:
    """Get VAPI assistant configuration to check if dial-keypad-dtmf tool is enabled."""
    headers = _get_vapi_headers(api_key)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.vapi.ai/assistant/{assistant_id}",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def create_vapi_call(
    api_key: str,
    assistant_id: str,
    phone_number_id: str,
    daily_phone_number: str,
    dialin_code: str,
) -> dict:
    """Create a VAPI call with the static phone/PIN."""
    headers = _get_vapi_headers(api_key)

    # Format phone number to E.164 format (ensure it has + prefix)
    formatted_phone = daily_phone_number.strip()
    if not formatted_phone.startswith("+"):
        formatted_phone = f"+{formatted_phone}"

    # Build the request payload
    # The dialin_code already includes the # at the end
    #
    # IMPORTANT: The dial-keypad-dtmf tool must be:
    # 1. Enabled in your VAPI assistant configuration
    # 2. The assistant must be instructed (via system message) to call it immediately
    #    when the call connects, reading the PIN from metadata.dialin_code
    #
    # Example system message for your VAPI assistant:
    # "When the call connects, immediately use the dial-keypad-dtmf tool to dial
    #  the digits from metadata.dialin_code. Do not wait for any prompts."
    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": formatted_phone,  # Daily.co phone number to dial
        },
        "metadata": {
            "dialin_code": dialin_code,  # PIN code + # for DTMF dialing
        },
    }

    print("\n📞 Creating VAPI call:")
    print(f"   Phone: {daily_phone_number}")
    print(f"   PIN: {dialin_code}")
    print(f"   Full payload: {payload}\n")
    print("⚠️  IMPORTANT: Your VAPI assistant must be configured to:")
    print("   1. Have the 'dial-keypad-dtmf' tool enabled")
    print("   2. Have a system message that tells it to call the tool immediately")
    print("      when the call connects, using metadata.dialin_code")
    print("   3. Example system message:")
    print("      'When the call connects, immediately use dial-keypad-dtmf tool'")
    print("      'to dial the digits from metadata.dialin_code. Do not wait.'\n")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.vapi.ai/call",
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def main():
    """Make VAPI call with static phone/PIN."""
    load_dotenv()

    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")
    vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

    if not all([vapi_api_key, vapi_assistant_id, vapi_phone_number_id]):
        missing = []
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

    print(f"\n{'='*80}")
    print("📞 Making VAPI call with static values:")
    print(f"   Phone: {STATIC_PHONE}")
    print(f"   PIN: {STATIC_PIN}")
    print(f"{'='*80}\n")

    # Check assistant configuration
    print("🔍 Checking assistant configuration...")
    try:
        assistant_config = await get_assistant_config(vapi_api_key, vapi_assistant_id)
        tools = assistant_config.get("tools", [])
        has_dtmf_tool = any(tool.get("type") == "dial-keypad-dtmf" for tool in tools)

        if has_dtmf_tool:
            print("   ✅ dial-keypad-dtmf tool is enabled")
        else:
            print("   ⚠️  dial-keypad-dtmf tool is NOT enabled!")
            print("   ⚠️  You need to enable it in your VAPI assistant configuration")
            print("   ⚠️  Go to: https://dashboard.vapi.ai/assistants")

        # Check system message
        messages = assistant_config.get("messages", [])
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        if system_messages:
            system_content = system_messages[0].get("content", "")
            if (
                "dial-keypad-dtmf" in system_content.lower()
                or "dtmf" in system_content.lower()
            ):
                print("   ✅ System message mentions DTMF/dial-keypad-dtmf")
            else:
                print("   ⚠️  System message doesn't mention dial-keypad-dtmf")
                print("   ⚠️  Add instruction to call the tool when call connects")
        else:
            print("   ⚠️  No system message found")

        print()
    except Exception as e:
        print(f"   ⚠️  Could not check assistant config: {e}\n")

    try:
        result = await create_vapi_call(
            api_key=vapi_api_key,
            assistant_id=vapi_assistant_id,
            phone_number_id=vapi_phone_number_id,
            daily_phone_number=STATIC_PHONE,
            dialin_code=STATIC_PIN,
        )

        call_id = result.get("id")
        print("✅ VAPI call created successfully!")
        print(f"   Call ID: {call_id}")
        print(
            f"\n   VAPI is now dialing {STATIC_PHONE} and will enter PIN {STATIC_PIN}"
        )
        print("   The call should connect shortly!\n")

    except Exception as e:
        print(f"❌ Failed to create VAPI call: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print(f"{'='*80}")
    print("✅ Done! VAPI call is in progress.")
    print("   Press Ctrl+C to exit")
    print(f"{'='*80}\n")

    # Keep running so user can observe
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Exiting...\n")


if __name__ == "__main__":
    asyncio.run(main())
