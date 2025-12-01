#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Script to list and release Daily.co phone numbers.

This script helps you manage your Daily.co phone numbers:
1. It shows you all the phone numbers you've purchased
2. You can select which one to release (delete) if you don't need it anymore

Usage:
    python flow/scripts/manage_daily_phone_numbers.py
    # Or with custom API key:
    DAILY_API_KEY=your-key python flow/scripts/manage_daily_phone_numbers.py

To release a specific phone number:
    python flow/scripts/manage_daily_phone_numbers.py --release <phone_number_id>
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv


def get_daily_headers(api_key: str) -> Dict[str, str]:
    """
    Get HTTP headers for Daily.co API requests.

    This function creates the headers (like authentication info) that
    we need to send with every request to Daily.co's API.

    Args:
        api_key: Your Daily.co API key

    Returns:
        Dictionary with headers including Authorization
    """
    auth_header = api_key.strip()
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }


async def list_purchased_phone_numbers(api_key: str) -> Dict[str, Any]:
    """
    List all purchased phone numbers from Daily.co.

    This function calls Daily.co's API to get a list of all phone numbers
    you've purchased. It's like asking "what phone numbers do I own?"

    Args:
        api_key: Daily.co API key

    Returns:
        Dictionary with phone numbers data from the API
    """
    headers = get_daily_headers(api_key)

    try:
        async with httpx.AsyncClient() as client:
            endpoint = "https://api.daily.co/v1/purchased-phone-numbers"

            response = await client.get(
                endpoint,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = error_data.get("error", {}).get("message", str(e))
            print(
                f"❌ Daily.co API error: {error_detail} (status: {e.response.status_code})"
            )
        except Exception:
            print(f"❌ Daily.co API error: {e}")
        return {}
    except Exception as e:
        print(f"❌ Failed to fetch phone numbers: {e}")
        return {}


async def release_phone_number(api_key: str, phone_number_id: str) -> bool:
    """
    Release (delete) a phone number from Daily.co.

    This function tells Daily.co to release (delete) a phone number you own.
    Once released, you won't be charged for it anymore, but you also won't
    be able to use it. This action cannot be undone!

    Args:
        api_key: Daily.co API key
        phone_number_id: The ID of the phone number to release

    Returns:
        True if successful, False otherwise
    """
    headers = get_daily_headers(api_key)

    try:
        async with httpx.AsyncClient() as client:
            # According to Daily.co docs: DELETE /v1/release-phone-number/{phone_number_id}
            # Match the curl exactly: Content-Type and Authorization headers, DELETE method
            endpoint = f"https://api.daily.co/v1/release-phone-number/{phone_number_id}"

            # The curl uses: Content-Type: application/json and Authorization: Bearer $API_KEY
            response = await client.delete(
                endpoint,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()

            return True

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_detail = (
                error_data.get("error", {}).get("message")
                or error_data.get("message")
                or str(error_data)
            )
            print(f"❌ Daily.co API error: {error_detail}")
            print(f"   Status code: {e.response.status_code}")
            print(f"   Full error response: {json.dumps(error_data, indent=2)}")
        except Exception:
            print(f"❌ Daily.co API error: {e}")
            print(f"   Status code: {e.response.status_code}")
            try:
                print(f"   Response text: {e.response.text}")
            except Exception:
                pass
        return False
    except Exception as e:
        print(f"❌ Failed to release phone number: {e}")
        return False


def display_phone_numbers(phone_numbers: List[Dict[str, Any]]) -> None:
    """
    Display phone numbers in a nice format.

    This function takes the list of phone numbers and prints them out
    in a readable format so you can see what you have.

    Args:
        phone_numbers: List of phone number dictionaries
    """
    if not phone_numbers:
        print("⚠️  No phone numbers found.")
        return

    print(f"\n📋 Your purchased phone numbers ({len(phone_numbers)} total):")
    print("=" * 80)

    for i, phone in enumerate(phone_numbers, 1):
        phone_id = phone.get("id", "N/A")
        phone_number = phone.get("number", "N/A")
        phone_type = phone.get("type", "N/A")
        created_at = phone.get("created_date") or phone.get("created_at", "N/A")

        print(f"\n  {i}. Phone Number: {phone_number}")
        print(f"     ID: {phone_id}")
        print(f"     Type: {phone_type}")
        print(f"     Created: {created_at}")

    print("\n" + "=" * 80)


async def main():
    """
    Main function that runs the script.

    This is the main function that runs when you execute the script.
    It:
    1. Loads your API key from environment variables
    2. Lists all your phone numbers
    3. If you want to release one, it asks which one and releases it
    """
    # by passing --release <phone_number_id> as command line arguments
    # Also check for --yes flag to skip confirmation
    release_id: Optional[str] = None
    skip_confirmation = False

    if len(sys.argv) > 1:
        if sys.argv[1] == "--release" and len(sys.argv) > 2:
            release_id = sys.argv[2]
            # Check if --yes flag is present
            if "--yes" in sys.argv or "-y" in sys.argv:
                skip_confirmation = True
        elif sys.argv[1] in ["-h", "--help"]:
            print(__doc__)
            sys.exit(0)
        else:
            print(
                "❌ Invalid arguments. Use --release <phone_number_id> [--yes] or --help"
            )
            sys.exit(1)

    # This lets us use DAILY_API_KEY from the .env file
    env_paths = [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    # This is like your password to access Daily.co's API
    api_key = os.getenv("DAILY_API_KEY")

    if not api_key:
        print("❌ Error: DAILY_API_KEY environment variable not set")
        print("\nUsage:")
        print(
            "  DAILY_API_KEY=your-key python flow/scripts/manage_daily_phone_numbers.py"
        )
        print("\nOr set it in your .env file:")
        print("  DAILY_API_KEY=your-key")
        print("\nTo release a phone number:")
        print(
            "  python flow/scripts/manage_daily_phone_numbers.py --release <phone_number_id>"
        )
        sys.exit(1)

    print("📞 Fetching purchased phone numbers from Daily.co...")
    print()

    result = await list_purchased_phone_numbers(api_key)

    # But also check if result is None or empty
    if result is None or (isinstance(result, dict) and not result):
        print("⚠️  Could not fetch phone numbers via API.")
        print()
        print("This could mean:")
        print("  1. You don't have any purchased phone numbers yet")
        print("  2. The API endpoint structure may have changed")
        print("  3. Phone numbers feature may require a specific Daily.co plan")
        print("  4. There was an API error (check error messages above)")
        print()
        print("💡 To check/manage phone numbers:")
        print("  1. Go to: https://dashboard.daily.co/phone-numbers")
        print("  2. You'll see all your purchased phone numbers there")
        sys.exit(0)

    # This helps us understand the API response format
    print(f"🔍 Debug: API Response structure: {json.dumps(result, indent=2)}")
    print()

    # The API returns data in a specific format, so we extract what we need
    # Daily.co API can return different formats, so we check multiple possibilities
    total_count = result.get("total_count", 0)
    phone_numbers_list = result.get("phone_numbers", [])
    phone_ids = result.get("ids", [])

    # Based on the actual API response, it returns: { "total_count": N, "data": [...] }
    if "data" in result:
        data = result.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            # The data array contains the phone number objects directly
            phone_numbers_list = data
            # Extract IDs from the data array
            phone_ids = [item.get("id") for item in data if item.get("id")]
            # Update total_count if we have data
            if total_count == 0 and len(data) > 0:
                total_count = len(data)

    # Sometimes the API returns just strings, sometimes objects, so we normalize them
    phone_numbers: List[Dict[str, Any]] = []

    if phone_numbers_list:
        if isinstance(phone_numbers_list[0], str):
            # If it's just a list of phone number strings
            for i, phone_num in enumerate(phone_numbers_list):
                phone_numbers.append(
                    {
                        "number": phone_num,
                        "id": phone_ids[i] if i < len(phone_ids) else f"unknown-{i}",
                    }
                )
        else:
            # If it's already a list of objects
            phone_numbers = phone_numbers_list

    # Sometimes the API doesn't return total_count correctly
    if total_count == 0 and len(phone_numbers) > 0:
        total_count = len(phone_numbers)

    if total_count == 0 and len(phone_numbers) == 0:
        print("⚠️  You don't have any purchased phone numbers yet.")
        print()
        print("To purchase a phone number:")
        print("1. Go to https://dashboard.daily.co/phone-numbers")
        print("2. Click 'Buy Phone Number'")
        print("3. Select a number and purchase it")
        sys.exit(0)

    display_phone_numbers(phone_numbers)

    # release that specific phone number
    if release_id:
        print(f"\n⚠️  WARNING: You are about to release phone number ID: {release_id}")
        print("   This action cannot be undone!")
        print(
            "   You will stop being charged for this number, but you won't be able to use it anymore."
        )
        print()

        # Find the phone number details to show user
        phone_to_release = None
        for phone in phone_numbers:
            if phone.get("id") == release_id:
                phone_to_release = phone
                break

        if phone_to_release:
            print(f"   Phone Number: {phone_to_release.get('number')}")
            print(f"   ID: {phone_to_release.get('id')}")
            print()

        if not skip_confirmation:
            confirm = (
                input("   Are you sure you want to release this number? (yes/no): ")
                .strip()
                .lower()
            )

            if confirm not in ["yes", "y"]:
                print("\n❌ Release cancelled.")
                sys.exit(0)
        else:
            print("   ⚠️  Skipping confirmation (--yes flag provided)")

        print(f"\n🔄 Releasing phone number {release_id}...")
        success = await release_phone_number(api_key, release_id)

        if success:
            print(f"✅ Successfully released phone number {release_id}!")
            print(
                "\n💡 The phone number has been released and you will no longer be charged for it."
            )
        else:
            print(f"❌ Failed to release phone number {release_id}.")
            print("   Please check the error message above.")
            sys.exit(1)
    else:
        print("\n💡 To release a phone number, run:")
        print(
            "   python flow/scripts/manage_daily_phone_numbers.py --release <phone_number_id>"
        )
        print("\n   Example:")
        if phone_numbers:
            example_id = phone_numbers[0].get("id", "phone_number_id")
            print(
                f"   python flow/scripts/manage_daily_phone_numbers.py --release {example_id}"
            )


if __name__ == "__main__":
    asyncio.run(main())
