#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Get Daily.co Meeting Information

This script fetches meeting information from Daily.co's API for a specific room.
It displays the complete meeting data structure, with special focus on how
participants are represented in the response.

**What this script does:**
1. Reads your DAILY_API_KEY from environment variables
2. Makes an API call to Daily.co to get meeting information for a room
3. Displays the full meeting data structure in a readable format
4. Highlights participant information so you can see how it's structured

**Usage:**
    python flow/scripts/get_meeting_info.py <room_name>

**Example:**
    python flow/scripts/get_meeting_info.py DEV-05122025120822933916

**Required Environment Variables:**
- DAILY_API_KEY: Your Daily.co API key (get it from https://dashboard.daily.co/)

**API Endpoint Used:**
- GET https://api.daily.co/v1/meetings?room=<room_name>

**Documentation:**
- https://docs.daily.co/reference/rest-api/meetings/get-meeting-information
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv

    # Load .env from flow/ directory or parent directory
    env_paths = [
        Path(__file__).parent.parent / ".env",  # flow/.env
        Path(__file__).parent.parent.parent / ".env",  # project root .env
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass


def get_daily_api_key() -> str:
    """
    Get Daily.co API key from environment variable.

    This function:
    1. Looks for DAILY_API_KEY in your environment
    2. If not found, shows helpful error message
    3. Returns the API key (stripped of whitespace)
    """
    api_key = os.getenv("DAILY_API_KEY")
    if not api_key:
        print("❌ Error: DAILY_API_KEY environment variable is not set")
        print("   Set it in your .env file or export it:")
        print("   export DAILY_API_KEY=your-api-key-here")
        print("\n   Or create a .env file in the flow/ directory with:")
        print("   DAILY_API_KEY=your-api-key-here")
        sys.exit(1)
    return api_key.strip()


def get_meeting_info(room_name: str) -> dict:
    """
    Fetch meeting information from Daily.co API.

    **What this function does:**
    1. Gets your API key
    2. Sets up HTTP headers with authentication
    3. Makes a GET request to Daily.co's meetings endpoint
    4. Returns the JSON response as a Python dictionary

    **Parameters:**
    - room_name: The name of the Daily.co room (e.g., "DEV-05122025120822933916")

    **Returns:**
    - Dictionary containing meeting information from Daily.co
    """
    api_key = get_daily_api_key()

    # Set up HTTP headers
    # Daily.co requires "Bearer" prefix for the API key
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Build the API URL
    # The endpoint is /v1/meetings with a "room" query parameter
    url = f"https://api.daily.co/v1/meetings?room={room_name}"

    print(f"📡 Making API request to: {url}")
    print(f"   Room: {room_name}\n")

    try:
        # Use httpx to make the HTTP request
        # httpx.Client() creates a connection that we can reuse
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)

            # Check if the request was successful
            # raise_for_status() will raise an error if status code is 4xx or 5xx
            response.raise_for_status()

            # Parse the JSON response into a Python dictionary
            result = response.json()

            # Daily.co API might return data in different formats:
            # - Direct list: [meeting1, meeting2, ...]
            # - Wrapped in object: {"data": [meeting1, meeting2, ...]}
            # We handle both cases
            if isinstance(result, list):
                return {"data": result}
            elif isinstance(result, dict) and "data" in result:
                return result
            else:
                # If it's a single meeting object, wrap it
                return {"data": [result]} if result else {"data": []}

    except httpx.HTTPStatusError as e:
        # Handle HTTP errors (like 404, 401, 500, etc.)
        print(f"❌ HTTP Error: {e.response.status_code}")
        try:
            error_data = e.response.json()
            print(f"   Error details: {json.dumps(error_data, indent=2)}")
        except (json.JSONDecodeError, ValueError):
            print(f"   Error message: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        # Handle any other errors (network issues, etc.)
        print(f"❌ Error fetching meeting info: {e}")
        sys.exit(1)


def print_meeting_info(meeting_data: dict):
    """
    Print meeting information in a readable format.

    **What this function does:**
    1. Displays the complete meeting data structure
    2. Highlights participant information separately
    3. Shows all fields so you can understand the data shape

    **Parameters:**
    - meeting_data: Dictionary containing meeting information from Daily.co
    """
    meetings = meeting_data.get("data", [])

    if not meetings:
        print("⚠️  No meetings found for this room.")
        print("   This could mean:")
        print("   - The room hasn't had any meetings yet")
        print("   - The room name is incorrect")
        print("   - The meetings are outside the default timeframe")
        return

    print(f"✅ Found {len(meetings)} meeting(s)\n")
    print("=" * 80)

    # Loop through each meeting and display its information
    for idx, meeting in enumerate(meetings, 1):
        print(f"\n📹 Meeting #{idx}")
        print("=" * 80)

        # Print the complete meeting object structure
        print("\n📋 Complete Meeting Data Structure:")
        print("-" * 80)
        print(json.dumps(meeting, indent=2))

        # Extract and highlight participant information
        print("\n" + "=" * 80)
        print("👥 PARTICIPANT INFORMATION (Highlighted)")
        print("=" * 80)

        # Check different possible locations for participant data
        # Daily.co might store participants in different fields
        participants = (
            meeting.get("participants")
            or meeting.get("participant")
            or meeting.get("participants_data")
            or meeting.get("participant_data")
            or []
        )

        if participants:
            print(f"\n✅ Found {len(participants)} participant(s):\n")
            for p_idx, participant in enumerate(participants, 1):
                print(f"   Participant #{p_idx}:")
                print(f"   {json.dumps(participant, indent=6)}")
                print()
        else:
            print("\n⚠️  No participants found in the meeting data.")
            print("   This could mean:")
            print("   - The meeting hasn't started yet")
            print("   - The meeting has ended and participants were cleared")
            print("   - Participants are stored in a different field")
            print("\n   Checking all fields in the meeting object...")

            # Show all top-level keys to help debug
            print("\n   Available fields in meeting object:")
            for key in meeting.keys():
                value = meeting[key]
                value_type = type(value).__name__
                if isinstance(value, (dict, list)):
                    print(
                        f"   - {key} ({value_type}): {len(value) if hasattr(value, '__len__') else 'N/A'} items"
                    )
                else:
                    print(f"   - {key} ({value_type}): {value}")

        print("\n" + "=" * 80)


def main():
    """
    Main function that runs the script.

    **What this function does:**
    1. Checks command line arguments (needs room name)
    2. Gets the API key from environment
    3. Fetches meeting information
    4. Displays the results
    """
    # Check if room name was provided as command line argument
    if len(sys.argv) < 2:
        print("Usage: python flow/scripts/get_meeting_info.py <room_name>")
        print("\nExample:")
        print("  python flow/scripts/get_meeting_info.py DEV-05122025120822933916")
        print("\nThis script will:")
        print("  1. Fetch meeting information from Daily.co API")
        print("  2. Display the complete meeting data structure")
        print("  3. Highlight participant information")
        sys.exit(1)

    room_name = sys.argv[1]

    print("=" * 80)
    print("🔍 Daily.co Meeting Information Fetcher")
    print("=" * 80)
    print(f"\nRoom: {room_name}")
    print()

    # Fetch the meeting information
    meeting_data = get_meeting_info(room_name)

    # Display the results
    print_meeting_info(meeting_data)

    print("\n" + "=" * 80)
    print("✅ Done!")
    print("=" * 80)


if __name__ == "__main__":
    main()
