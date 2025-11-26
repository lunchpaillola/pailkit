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
STATIC_PIN = "69233926034#"


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

    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": formatted_phone,
        },
        "metadata": {
            "dialin_code": dialin_code,
        },
    }

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

    print(f"📞 Making VAPI call: {STATIC_PHONE} (PIN: {STATIC_PIN})")

    result = await create_vapi_call(
        api_key=vapi_api_key,
        assistant_id=vapi_assistant_id,
        phone_number_id=vapi_phone_number_id,
        daily_phone_number=STATIC_PHONE,
        dialin_code=STATIC_PIN,
    )

    call_id = result.get("id")
    print(f"✅ Call created: {call_id}")


if __name__ == "__main__":
    asyncio.run(main())
