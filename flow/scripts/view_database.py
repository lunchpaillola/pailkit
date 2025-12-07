#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
View Supabase Database Contents

Simple script to view what's stored in the Supabase database.

Run with: python flow/scripts/view_database.py
"""

import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

from flow.db import get_supabase_client, get_session_data  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()


def format_session_data(session_data: dict, room_name: str, created_at: str = None):
    """
    Format and display session data for a room.

    Args:
        session_data: Dictionary containing session data (already decrypted)
        room_name: Room identifier
        created_at: Optional timestamp string
    """
    print(f"{'='*80}")
    print(f"Room: {room_name}")
    if created_at:
        print(f"Created: {created_at}")
    print(f"{'-'*80}")

    try:
        print("\n📦 Session Data (decrypted):")
        for key, value in session_data.items():
            # Special handling for transcript_text - show it fully
            if key == "transcript_text" and value:
                print(f"\n   📝 {key}:")
                print("   " + "=" * 76)
                # Show transcript with proper formatting
                transcript_lines = str(value).split("\n")
                for line in transcript_lines[:50]:  # Show first 50 lines
                    if line.strip():
                        print(f"   {line}")
                if len(transcript_lines) > 50:
                    print(f"   ... ({len(transcript_lines) - 50} more lines)")
                print("   " + "=" * 76)
            else:
                # Truncate long values for readability
                display_value = str(value)
                if len(display_value) > 100:
                    display_value = display_value[:100] + "..."
                print(f"   {key}: {display_value}")
    except Exception as e:
        print(f"   ⚠️ Error displaying data: {e}")

    print()


def view_database():
    """Display all session data from Supabase database."""
    print(f"\n{'='*80}")
    print("📊 Supabase Database Viewer")
    print(f"{'='*80}\n")

    client = get_supabase_client()
    if not client:
        print(
            "❌ Cannot connect to Supabase. Check your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
        return

    try:
        # Get all rooms ordered by created_at
        response = (
            client.table("rooms").select("*").order("created_at", desc=True).execute()
        )

        if not response.data or len(response.data) == 0:
            print("📭 Database is empty. No session data stored yet.")
            return

        print(f"📋 Found {len(response.data)} room session(s):\n")

        for i, row in enumerate(response.data, 1):
            room_name = row.get("room_name")
            created_at = row.get("created_at")

            # Get session data using the helper function (handles decryption)
            session_data = get_session_data(room_name)

            if session_data:
                format_session_data(session_data, room_name, created_at)
            else:
                print(f"{'='*80}")
                print(f"Room #{i}: {room_name}")
                print(f"Created: {created_at}")
                print(f"{'-'*80}")
                print("   ⚠️ Could not retrieve session data")
                print()

        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ Error reading from Supabase: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    view_database()


if __name__ == "__main__":
    view_database()
