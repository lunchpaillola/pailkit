# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
SQLite Database Helper for PailFlow

Simple database to store session data for interview rooms.
This replaces Daily.co's session data API for better control and reliability.

**Security:**
Sensitive fields (candidate info, emails, webhooks, transcripts) are encrypted
at rest using field-level encryption. Operational fields (IDs, timestamps) remain
unencrypted for querying. The encryption key is stored in the ENCRYPTION_KEY
environment variable.
"""

import base64
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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

# Fields that should be encrypted (sensitive candidate data)
ENCRYPTED_FIELDS = {
    "candidate_email",
    "candidate_name",
    "webhook_callback_url",
    "email_results_to",
    "interviewer_context",
    "transcript_text",
    "candidate_summary",
}

# Fields that should remain unencrypted (operational)
UNENCRYPTED_FIELDS = {
    "room_name",
    "session_id",
    "created_at",
    "interview_type",
    "difficulty_level",
    "position",  # Could be encrypted, but keeping unencrypted for now
}


def get_encryption_key() -> bytes:
    """
    Get the encryption key and convert it to a Fernet key.

    **Simple Explanation:**
    This function retrieves the encryption key from the ENCRYPTION_KEY
    environment variable and converts it to a format that Fernet can use.
    Fernet requires a 32-byte key, so we derive it from the user's key using
    PBKDF2 (a key derivation function).

    Returns:
        Fernet encryption key as bytes

    Raises:
        ValueError: If ENCRYPTION_KEY is not set or is too short
    """
    encryption_key_str = os.getenv("ENCRYPTION_KEY")
    if not encryption_key_str:
        raise ValueError(
            "ENCRYPTION_KEY environment variable is required for field encryption. "
            "Set it in your .env file with a strong random key (at least 32 characters)."
        )

    # Validate key length
    if len(encryption_key_str) < 32:
        raise ValueError(
            f"ENCRYPTION_KEY must be at least 32 characters long. "
            f"Current length: {len(encryption_key_str)}. "
            f'Generate a strong key with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )

    # Derive a 32-byte key from the user's key using PBKDF2
    # **Simple Explanation:** PBKDF2 is a key derivation function that takes
    # a password/key and converts it into a fixed-length encryption key.
    # We use a salt (a random value) to make the key derivation more secure.
    salt = b"pailflow_salt_2025"  # Fixed salt - in production, consider making this configurable
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,  # Number of iterations (higher = more secure but slower)
    )
    key = base64.urlsafe_b64encode(kdf.derive(encryption_key_str.encode()))
    return key


def get_fernet() -> Fernet:
    """
    Get a Fernet encryption instance.

    **Simple Explanation:**
    Fernet is a symmetric encryption algorithm that provides authenticated
    encryption. It ensures that encrypted data cannot be tampered with and
    can only be decrypted with the correct key.

    Returns:
        Fernet instance for encryption/decryption
    """
    key = get_encryption_key()
    return Fernet(key)


def encrypt_field(value: str | None) -> str | None:
    """
    Encrypt a sensitive field value.

    **Simple Explanation:**
    This function takes a string value (like an email or name) and encrypts it.
    If the value is None or empty, it returns None (no encryption needed).

    Args:
        value: The string value to encrypt

    Returns:
        Encrypted value as base64 string, or None if input was None/empty
    """
    if not value or value.strip() == "":
        return None

    try:
        fernet = get_fernet()
        encrypted = fernet.encrypt(value.encode())
        # Return as base64 string for easy storage in JSON/database
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"❌ Error encrypting field: {e}", exc_info=True)
        raise


def decrypt_field(value: str | None) -> str | None:
    """
    Decrypt a sensitive field value.

    **Simple Explanation:**
    This function takes an encrypted string and decrypts it back to the
    original value. If the value is None or empty, it returns None.

    Args:
        value: The encrypted value as base64 string

    Returns:
        Decrypted value as string, or None if input was None/empty
    """
    if not value or value.strip() == "":
        return None

    try:
        fernet = get_fernet()
        # Decode from base64 first
        encrypted_bytes = base64.urlsafe_b64decode(value.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"❌ Error decrypting field: {e}", exc_info=True)
        raise


def encrypt_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Encrypt sensitive fields in a dictionary.

    **Simple Explanation:**
    This function goes through a dictionary and encrypts any fields that
    contain sensitive information (like emails, names, webhooks). It leaves
    operational fields (like IDs, timestamps) unencrypted.

    Args:
        data: Dictionary containing session data

    Returns:
        Dictionary with sensitive fields encrypted
    """
    encrypted_data = data.copy()

    for key, value in encrypted_data.items():
        # Encrypt if it's a sensitive field and has a value
        if key in ENCRYPTED_FIELDS and value is not None:
            if isinstance(value, str):
                encrypted_data[key] = encrypt_field(value)
            elif isinstance(value, dict):
                # Recursively encrypt nested dictionaries
                encrypted_data[key] = encrypt_sensitive_data(value)
            elif isinstance(value, list):
                # Encrypt each item in the list if it's a string
                encrypted_data[key] = [
                    encrypt_field(item) if isinstance(item, str) else item
                    for item in value
                ]

    return encrypted_data


def decrypt_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decrypt sensitive fields in a dictionary.

    **Simple Explanation:**
    This function goes through a dictionary and decrypts any fields that
    were encrypted. It leaves operational fields unchanged.

    Args:
        data: Dictionary containing encrypted session data

    Returns:
        Dictionary with sensitive fields decrypted
    """
    decrypted_data = data.copy()

    for key, value in decrypted_data.items():
        # Decrypt if it's a sensitive field and has a value
        if key in ENCRYPTED_FIELDS and value is not None:
            if isinstance(value, str):
                # Try to decrypt - if it fails, assume it's not encrypted (backward compatibility)
                try:
                    decrypted_data[key] = decrypt_field(value)
                except Exception:
                    # If decryption fails, assume it's already unencrypted (for migration)
                    logger.debug(
                        f"Field {key} appears to be unencrypted, skipping decryption"
                    )
                    pass
            elif isinstance(value, dict):
                # Recursively decrypt nested dictionaries
                decrypted_data[key] = decrypt_sensitive_data(value)
            elif isinstance(value, list):
                # Decrypt each item in the list if it's a string
                decrypted_data[key] = [
                    decrypt_field(item) if isinstance(item, str) else item
                    for item in value
                ]

    return decrypted_data


def get_db_connection():
    """
    Get a regular SQLite database connection.

    **Simple Explanation:**
    Since we're using field-level encryption instead of full database encryption,
    we use a regular SQLite connection. The encryption happens at the field level
    before storing data.

    Returns:
        sqlite3.Connection object
    """
    return sqlite3.connect(str(DB_PATH))


def init_db() -> None:
    """
    Initialize the database and create tables if they don't exist.

    **Simple Explanation:**
    This function sets up the SQLite database for the first time.
    It creates a table called 'room_sessions' that stores session data
    for each room. Sensitive fields are encrypted at the field level.

    The table has:
    - room_name: The unique identifier for the room (e.g., "abc123") - unencrypted
    - session_data: A JSON blob containing session information (sensitive fields encrypted)
    - created_at: Timestamp when the record was created - unencrypted

    **Security:**
    - Sensitive fields (emails, names, webhooks, transcripts) are encrypted at rest
    - Operational fields (IDs, timestamps) remain unencrypted for querying
    - File permissions are set to 0o600 (only owner can read/write)
    - Encryption key is stored in ENCRYPTION_KEY environment variable
    """
    try:
        # Create parent directory if it doesn't exist (for /data on Fly.io)
        # **Simple Explanation:** On Fly.io, the /data directory might not exist
        # until the volume is mounted, but we want to create it if needed.
        # SQLite will create the file, but we need the directory to exist first.
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Get database connection
        conn = get_db_connection()
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

        # Set restrictive file permissions (only owner can read/write)
        # **Simple Explanation:** This adds an extra layer of security by
        # ensuring only the owner of the file can access it, even if someone
        # gets access to the file system.
        try:
            os.chmod(DB_PATH, 0o600)  # rw------- (only owner)
            logger.info("✅ Database file permissions set to 0o600")
        except Exception as perm_error:
            logger.warning(
                f"⚠️ Could not set file permissions (this is okay on some systems): {perm_error}"
            )

        logger.info(
            f"✅ Database initialized at {DB_PATH} (field-level encryption enabled)"
        )

    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}", exc_info=True)
        raise


def save_session_data(room_name: str, session_data: Dict[str, Any]) -> bool:
    """
    Save session data for a room to the database with field-level encryption.

    **Simple Explanation:**
    This function stores session data in the database when a room is created.
    Before saving, it encrypts sensitive fields (emails, names, webhooks) while
    keeping operational fields (IDs, timestamps) unencrypted.

    If data already exists for this room, it will be replaced (REPLACE INTO).

    Args:
        room_name: The room identifier (e.g., "abc123") - unencrypted
        session_data: Dictionary containing session information

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Encrypt sensitive fields before saving
        encrypted_data = encrypt_sensitive_data(session_data)

        # Convert session_data dict to JSON string
        session_json = json.dumps(encrypted_data)

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

        logger.info(
            f"✅ Session data saved for room: {room_name} (sensitive fields encrypted)"
        )
        return True

    except Exception as e:
        logger.error(
            f"❌ Error saving session data for {room_name}: {e}", exc_info=True
        )
        return False


def get_session_data(room_name: str) -> Dict[str, Any] | None:
    """
    Retrieve session data for a room from the database and decrypt sensitive fields.

    **Simple Explanation:**
    This function looks up session data for a room in the database.
    It decrypts sensitive fields (emails, names, webhooks) that were encrypted
    when saving. Operational fields remain unchanged.

    It's called by the webhook handler when a transcript is ready,
    so we know where to send the results and who the candidate is.

    Args:
        room_name: The room identifier (e.g., "abc123")

    Returns:
        Dictionary with session data (sensitive fields decrypted), or None if not found
    """
    try:
        conn = get_db_connection()
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
            # Decrypt sensitive fields
            decrypted_data = decrypt_sensitive_data(session_data)
            logger.info(
                f"✅ Retrieved session data for room: {room_name} (sensitive fields decrypted)"
            )
            return decrypted_data
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
        conn = get_db_connection()
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
