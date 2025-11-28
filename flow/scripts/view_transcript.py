#!/usr/bin/env python3.12
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
View transcript for a specific room.

Usage:
    python flow/scripts/view_transcript.py DEV-26112025235702154127
    python flow/scripts/view_transcript.py  # Shows most recent room
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

load_dotenv()

from flow.db import get_session_data  # noqa: E402


def view_transcript(room_name: str):
    """Display transcript for a specific room."""
    print(f"\n{'='*80}")
    print(f"📝 Transcript Viewer - Room: {room_name}")
    print(f"{'='*80}\n")

    session_data = get_session_data(room_name)

    if not session_data:
        print(f"❌ No session data found for room: {room_name}")
        return

    transcript_text = session_data.get("transcript_text")

    if not transcript_text:
        print("⚠️ No transcript found in session data.")
        print("\nThis could mean:")
        print("  - The call hasn't started yet")
        print("  - TranscriptProcessor hasn't captured any speech yet")
        print("  - The bot didn't join the room")
        return

    print("✅ Transcript found!\n")
    print("=" * 80)
    print("TRANSCRIPT:")
    print("=" * 80)
    print(transcript_text)
    print("=" * 80)
    print(f"\n📊 Transcript length: {len(transcript_text)} characters")
    print(f"📊 Lines: {len(transcript_text.split(chr(10)))}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        room_name = sys.argv[1]
    else:
        # Get most recent room
        import sqlite3
        from flow.db import get_db_path

        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT room_name FROM room_sessions
            ORDER BY created_at DESC
            LIMIT 1
        """
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            room_name = result[0]
            print(f"📋 Using most recent room: {room_name}\n")
        else:
            print("❌ No rooms found in database")
            sys.exit(1)

    view_transcript(room_name)
