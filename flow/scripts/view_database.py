#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
View SQLite Database Contents

Simple script to view what's stored in the session data database.

Run with: python flow/scripts/view_database.py
"""

import json
import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

from flow.db import get_db_path  # noqa: E402
import sqlite3  # noqa: E402


def view_database():
    """Display all session data in the database."""
    db_path = get_db_path()

    print(f"\n{'='*80}")
    print("📊 SQLite Database Viewer")
    print(f"{'='*80}\n")
    print(f"Database Location: {db_path}")
    print(f"Database Exists: {db_path.exists()}\n")

    if not db_path.exists():
        print("❌ Database file not found. No rooms have been created yet.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all room sessions
        cursor.execute(
            """
            SELECT room_name, session_data, created_at
            FROM room_sessions
            ORDER BY created_at DESC
        """
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("📭 Database is empty. No session data stored yet.")
            return

        print(f"📋 Found {len(rows)} room session(s):\n")

        for i, (room_name, session_data_json, created_at) in enumerate(rows, 1):
            print(f"{'='*80}")
            print(f"Room #{i}: {room_name}")
            print(f"Created: {created_at}")
            print(f"{'-'*80}")

            try:
                session_data = json.loads(session_data_json)
                print("\n📦 Session Data:")
                for key, value in session_data.items():
                    # Truncate long values for readability
                    display_value = str(value)
                    if len(display_value) > 100:
                        display_value = display_value[:100] + "..."
                    print(f"   {key}: {display_value}")
            except json.JSONDecodeError as e:
                print(f"   ⚠️ Error parsing JSON: {e}")
                print(f"   Raw data: {session_data_json[:200]}...")

            print()

        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ Error reading database: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    view_database()
