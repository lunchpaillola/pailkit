#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Kill All Running Bots

This script stops all active bot processes immediately.
Useful for cleaning up stuck bots or resetting the bot service.

Run with: python flow/scripts/kill_all_bots.py
"""

import asyncio
import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

from flow.steps.interview.bot_service import bot_service  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()


async def kill_all_bots():
    """
    Stop all running bots and display what was stopped.

    Simple Explanation:
    1. First, we list all active bots to see what's running
    2. Then we call cleanup() which stops all bot tasks
    3. Finally, we confirm they're all gone
    """
    print("🔍 Checking for active bots...")

    # List all active bots first
    active_bots = bot_service.list_active_bots()

    if not active_bots:
        print("✅ No active bots found - nothing to kill!")
        return

    print(f"\n📋 Found {len(active_bots)} active bot(s):")
    for room_name, status in active_bots.items():
        runtime_hours = status.get("runtime_hours", 0)
        is_running = status.get("is_running", False)
        print(f"   - Room: {room_name}")
        print(f"     Running: {is_running}")
        print(f"     Runtime: {runtime_hours:.2f} hours")
        if status.get("warning"):
            print(f"     ⚠️  {status['warning']}")

    print(f"\n🛑 Stopping all {len(active_bots)} bot(s)...")

    # Stop all bots
    await bot_service.cleanup()

    # Verify they're all gone
    remaining = bot_service.list_active_bots()
    if remaining:
        print(f"⚠️  Warning: {len(remaining)} bot(s) still running after cleanup")
        for room_name in remaining:
            print(f"   - {room_name}")
    else:
        print("✅ All bots stopped successfully!")


if __name__ == "__main__":
    # Simple Explanation: asyncio.run() creates an event loop, runs our async function,
    # and then closes the loop. This is the standard way to run async code from a script.
    try:
        asyncio.run(kill_all_bots())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
