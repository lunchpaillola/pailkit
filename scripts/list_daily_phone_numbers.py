#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Script to list purchased Daily.co phone numbers.

**Simple Explanation:**
This script checks what phone numbers you have purchased in Daily.co.
You need at least one phone number to enable PIN dial-in for rooms.

Usage:
    python scripts/list_daily_phone_numbers.py
    # Or with custom API key:
    DAILY_API_KEY=your-key python scripts/list_daily_phone_numbers.py
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict

import httpx

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load .env from project root (flow/ or api/ directory)
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
    """Get HTTP headers for Daily.co API requests."""
    auth_header = api_key.strip()
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }


def list_purchased_phone_numbers(api_key: str) -> Dict[str, Any]:
    """
    List all purchased phone numbers from Daily.co.

    **Simple Explanation:**
    This calls Daily.co's API to get a list of all phone numbers
    you've purchased. You need at least one to enable dial-in.

    Args:
        api_key: Daily.co API key

    Returns:
        Dictionary with phone numbers data
    """
    headers = get_daily_headers(api_key)

    try:
        async def fetch():
            async with httpx.AsyncClient() as client:
                # Use the correct endpoint: /purchased-phone-numbers
                endpoint = "https://api.daily.co/v1/purchased-phone-numbers"

                response = await client.get(
                    endpoint,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

        import asyncio
        return asyncio.run(fetch())

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", str(e))
            print(f"❌ Daily.co API error: {error_detail} (status: {e.response.status_code})")
        except Exception:
            print(f"❌ Daily.co API error: {e}")
        return {}
    except Exception as e:
        print(f"❌ Failed to fetch phone numbers: {e}")
        return {}


def main():
    """Main function to list phone numbers."""
    # Get API key from environment variable
    api_key = os.getenv("DAILY_API_KEY")

    if not api_key:
        print("❌ Error: DAILY_API_KEY environment variable not set")
        print("\nUsage:")
        print("  DAILY_API_KEY=your-key python scripts/list_daily_phone_numbers.py")
        print("\nOr set it in your .env file and load it:")
        print("  export DAILY_API_KEY=your-key")
        print("  python scripts/list_daily_phone_numbers.py")
        sys.exit(1)

    print("📞 Fetching purchased phone numbers from Daily.co...")
    print()

    result = list_purchased_phone_numbers(api_key)

    if not result:
        print("⚠️  Could not fetch phone numbers via API.")
        print()
        print("This could mean:")
        print("  1. You don't have any purchased phone numbers yet")
        print("  2. The API endpoint structure may have changed")
        print("  3. Phone numbers feature may require a specific Daily.co plan")
        print()
        print("💡 To check/manage phone numbers:")
        print("  1. Go to: https://dashboard.daily.co/phone-numbers")
        print("  2. You'll see all your purchased phone numbers there")
        print("  3. If you don't have any, click 'Buy Phone Number' to purchase one")
        print()
        print("✅ Good news: You don't need to specify a phone number when enabling")
        print("   PIN dial-in - Daily.co will automatically use your default")
        print("   (earliest purchased) phone number!")
        sys.exit(0)

    # Parse the response
    # Daily.co API returns: { "total_count": N, "ids": [...], "phone_numbers": [...] }
    total_count = result.get("total_count", 0)
    phone_numbers_list = result.get("phone_numbers", [])
    phone_ids = result.get("ids", [])

    # If phone_numbers is a list of strings, convert to list of dicts
    phone_numbers = []
    if phone_numbers_list and isinstance(phone_numbers_list[0], str):
        # If it's just a list of phone number strings
        for i, phone_num in enumerate(phone_numbers_list):
            phone_numbers.append({
                "number": phone_num,
                "id": phone_ids[i] if i < len(phone_ids) else f"unknown-{i}",
            })
    elif phone_numbers_list:
        # If it's already a list of objects
        phone_numbers = phone_numbers_list

    print(f"✅ Found {total_count} purchased phone number(s)")
    print()

    if total_count == 0:
        print("⚠️  You don't have any purchased phone numbers yet.")
        print()
        print("To purchase a phone number:")
        print("1. Go to https://dashboard.daily.co/phone-numbers")
        print("2. Click 'Buy Phone Number'")
        print("3. Select a number and purchase it")
        print()
        print("Note: Phone numbers are pay-as-you-go. Make sure you have")
        print("      a credit card added to your Daily.co account.")
        sys.exit(0)

    # Display phone numbers
    print("📋 Your purchased phone numbers:")
    print()
    for i, phone in enumerate(phone_numbers, 1):
        phone_id = phone.get("id", "N/A")
        phone_number = phone.get("number", "N/A")
        phone_type = phone.get("type", "N/A")
        created_at = phone.get("created_at", "N/A")

        print(f"  {i}. Phone Number: {phone_number}")
        print(f"     ID: {phone_id}")
        print(f"     Type: {phone_type}")
        print(f"     Created: {created_at}")
        print()

    print("✅ You're all set! You can use any of these phone numbers for dial-in.")
    print()
    print("💡 Tip: When enabling PIN dial-in, you can specify a phone number")
    print("         or let Daily.co use the default (earliest purchased) number.")


if __name__ == "__main__":
    main()
