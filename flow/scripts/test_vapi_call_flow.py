#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Create a room with VAPI and immediately check the call status.

This script:
1. Creates a room with VAPI enabled
2. Gets the VAPI call ID
3. Immediately checks the VAPI call status
4. Waits and polls the call status to see if it connects
"""

import asyncio
import importlib
import json
import os
import sys

import httpx
from dotenv import load_dotenv

# Add project root to path before importing project modules
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

# Import project module after modifying sys.path
# Using importlib to avoid E402 linting error for imports after sys.path modification
workflow_module = importlib.import_module("flow.workflows.one_time_meeting")
OneTimeMeetingWorkflow = workflow_module.OneTimeMeetingWorkflow


async def check_vapi_call_status(call_id: str, api_key: str) -> dict:
    """Check VAPI call status."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.vapi.ai/call/{call_id}",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"error": str(e)}


async def main():
    """Create room and check VAPI call status."""
    load_dotenv()

    daily_api_key = os.getenv("DAILY_API_KEY")
    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")
    vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

    if not all([daily_api_key, vapi_api_key, vapi_assistant_id, vapi_phone_number_id]):
        print("❌ Missing required API keys")
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

    print(f"\n{'='*80}")
    print("🚀 Creating room with VAPI...")
    print(f"{'='*80}\n")

    result = await workflow.execute_async(context)

    room_url = result.get("room_url")
    sip_uri = result.get("sip_uri")
    vapi_call_id = result.get("vapi_call_id")
    vapi_call_created = result.get("vapi_call_created", False)
    vapi_call_error = result.get("vapi_call_error")

    print(f"\n{'='*80}")
    print("📋 Workflow Result:")
    print(f"{'='*80}")
    print(json.dumps(result, indent=2, default=str))
    print(f"{'='*80}\n")

    if not vapi_call_created or not vapi_call_id:
        print("❌ VAPI call was not created")
        print(f"  vapi_call_created: {vapi_call_created}")
        print(f"  vapi_call_id: {vapi_call_id}")
        print(f"  Error: {vapi_call_error}")
        if room_url:
            print(f"\n✅ Room was created: {room_url}")
            print(f"   SIP URI: {sip_uri}")
        sys.exit(1)

    print(f"✅ Room created: {room_url}")
    print(f"✅ VAPI call created: {vapi_call_id}")
    print(f"📱 SIP URI: {sip_uri}\n")

    print(f"{'='*80}")
    print("📞 Checking VAPI Call Status...")
    print(f"{'='*80}\n")

    # Check call status immediately
    call_data = await check_vapi_call_status(vapi_call_id, vapi_api_key)

    if "error" in call_data:
        print(f"❌ Error checking call: {call_data['error']}")
        return

    print("Initial Call Status:")
    print(f"  Status: {call_data.get('status')}")
    print(f"  Created: {call_data.get('createdAt')}")

    customer = call_data.get("customer", {})
    if customer:
        print(f"  Customer SIP URI: {customer.get('sipUri')}")
        print(f"  Customer Number: {customer.get('number')}")

    print(f"\n{'='*80}")
    print("⏳ Polling call status (checking every 2 seconds for 30 seconds)...")
    print(f"{'='*80}\n")

    # Poll for 30 seconds to see status changes
    for i in range(15):  # 15 iterations * 2 seconds = 30 seconds
        await asyncio.sleep(2)
        call_data = await check_vapi_call_status(vapi_call_id, vapi_api_key)

        if "error" in call_data:
            print(f"❌ Error: {call_data['error']}")
            break

        status = call_data.get("status")
        elapsed = (i + 1) * 2

        print(f"  [{elapsed}s] Status: {status}", end="")

        # Check for end reason
        end_reason = call_data.get("endReason")
        if end_reason:
            print(f" | End Reason: {end_reason}")
        else:
            print()

        # If call ended, stop polling
        if status in ["ended", "failed"]:
            break

    print(f"\n{'='*80}")
    print("📊 Final Call Status:")
    print(f"{'='*80}\n")

    call_data = await check_vapi_call_status(vapi_call_id, vapi_api_key)
    print(json.dumps(call_data, indent=2))

    print(f"\n{'='*80}")
    print("💡 Summary:")
    print(f"{'='*80}")
    print(f"  Room URL: {room_url}")
    print(f"  VAPI Call ID: {vapi_call_id}")
    print(f"  Final Status: {call_data.get('status')}")
    print(f"  End Reason: {call_data.get('endReason', 'N/A')}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
