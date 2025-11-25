# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
SQLite Database Helper for PailFlow

Simple database to store session data for interview rooms.
This replaces Daily.co's session data API for better control and reliability.
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


# Database file location
# **Simple Explanation:**
# - On Fly.io: Uses /data/pailflow.db (persistent volume - survives restarts)
# - Locally: Uses flow/pailflow.db (in your project directory)
# - You can override with DB_PATH environment variable
def get_db_path() -> Path:
    """Get the database path, checking environment variable first, then Fly volume, then local."""
    # Check for explicit path override
    if db_path_env := os.getenv("DB_PATH"):
        return Path(db_path_env)

    # On Fly.io, use persistent volume at /data
    # **Simple Explanation:** Fly.io volumes are mounted at /data and persist across restarts
    fly_data_path = Path("/data/pailflow.db")
    if fly_data_path.parent.exists():
        return fly_data_path

    # Local development: use flow/ directory
    return Path(__file__).parent / "pailflow.db"


DB_PATH = get_db_path()


def init_db() -> None:
    """
    Initialize the database and create tables if they don't exist.

    **Simple Explanation:**
    This function sets up the SQLite database for the first time.
    It creates a table called 'room_sessions' that stores session data
    for each room. The table has:
    - room_name: The unique identifier for the room (e.g., "abc123")
    - session_data: A JSON blob containing all the session information
    - created_at: Timestamp when the record was created
    """
    try:
        # Create parent directory if it doesn't exist (for /data on Fly.io)
        # **Simple Explanation:** On Fly.io, the /data directory might not exist
        # until the volume is mounted, but we want to create it if needed.
        # SQLite will create the file, but we need the directory to exist first.
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Create room_sessions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS room_sessions (
                room_name TEXT PRIMARY KEY,
                session_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        conn.close()
        logger.info(f"✅ Database initialized at {DB_PATH}")

    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}", exc_info=True)
        raise


def save_session_data(room_name: str, session_data: Dict[str, Any]) -> bool:
    """
    Save session data for a room to the database.

    **Simple Explanation:**
    This function stores session data (like candidate name, email, webhook URL)
    in the database when a room is created. It uses JSON to convert the Python
    dictionary into a string that can be stored in SQLite.

    If data already exists for this room, it will be replaced (REPLACE INTO).

    Args:
        room_name: The room identifier (e.g., "abc123")
        session_data: Dictionary containing session information

    Returns:
        True if saved successfully, False otherwise
    """
    import json

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Convert session_data dict to JSON string
        session_json = json.dumps(session_data)

        # Use REPLACE to update if exists, insert if new
        cursor.execute(
            """
            REPLACE INTO room_sessions (room_name, session_data)
            VALUES (?, ?)
        """,
            (room_name, session_json),
        )

        conn.commit()
        conn.close()

        logger.info(f"✅ Session data saved for room: {room_name}")
        return True

    except Exception as e:
        logger.error(
            f"❌ Error saving session data for {room_name}: {e}", exc_info=True
        )
        return False


def get_session_data(room_name: str) -> Dict[str, Any] | None:
    """
    Retrieve session data for a room from the database.

    **Simple Explanation:**
    This function looks up session data for a room in the database.
    It's called by the webhook handler when a transcript is ready,
    so we know where to send the results and who the candidate is.

    Args:
        room_name: The room identifier (e.g., "abc123")

    Returns:
        Dictionary with session data, or None if not found
    """
    import json

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT session_data FROM room_sessions WHERE room_name = ?
        """,
            (room_name,),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            session_data = json.loads(result[0])
            logger.info(f"✅ Retrieved session data for room: {room_name}")
            return session_data
        else:
            logger.warning(f"⚠️ No session data found for room: {room_name}")
            return None

    except Exception as e:
        logger.error(
            f"❌ Error retrieving session data for {room_name}: {e}", exc_info=True
        )
        return None


def delete_session_data(room_name: str) -> bool:
    """
    Delete session data for a room (optional cleanup).

    **Simple Explanation:**
    This function removes session data from the database.
    You might call this after processing is complete to keep
    the database clean. This is optional - data can remain
    for debugging or audit purposes.

    Args:
        room_name: The room identifier (e.g., "abc123")

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM room_sessions WHERE room_name = ?
        """,
            (room_name,),
        )

        conn.commit()
        rows_deleted = cursor.rowcount
        conn.close()

        if rows_deleted > 0:
            logger.info(f"✅ Session data deleted for room: {room_name}")
            return True
        else:
            logger.warning(f"⚠️ No session data to delete for room: {room_name}")
            return False

    except Exception as e:
        logger.error(
            f"❌ Error deleting session data for {room_name}: {e}", exc_info=True
        )
        return False


# Initialize database on module import
init_db()
