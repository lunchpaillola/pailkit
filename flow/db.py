# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Supabase Database Helper for PailFlow

Database module for storing session data for interview rooms using Supabase (PostgreSQL).

**Security:**
Sensitive fields (candidate info, emails, webhooks, transcripts) are encrypted
at rest using field-level encryption. Operational fields (IDs, timestamps) remain
unencrypted for querying. The encryption key is stored in the ENCRYPTION_KEY
environment variable.
"""

import base64
import logging
import os
from typing import Any, Dict, TYPE_CHECKING

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Type checking imports (only used for type hints, not at runtime)
if TYPE_CHECKING:
    from supabase import Client

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

# Try to import Supabase client
try:
    from supabase import create_client, Client

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning(
        "⚠️ Supabase client not available. Install with: pip install supabase"
    )


def get_encryption_key() -> bytes:
    """
    Get the encryption key and convert it to a Fernet key.

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

    Returns:
        Fernet instance for encryption/decryption
    """
    key = get_encryption_key()
    return Fernet(key)


def encrypt_field(value: str | None) -> str | None:
    """
    Encrypt a sensitive field value.

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


def get_supabase_client() -> "Client | None":
    """
    Get a Supabase client instance for database operations.

    **Environment Variables Required:**
    - SUPABASE_URL: Your Supabase project URL (e.g., https://xxxxx.supabase.co)
    - SUPABASE_SERVICE_ROLE_KEY: Secret API key for backend operations (bypasses RLS)
      - Also called "secret" key in modern Supabase UI
      - Formerly called "service_role" key (legacy naming)
      - Use this for backend/server code - never expose in client-side code

    **For Local Development:**
    When running `supabase start`, you'll get local connection details.
    Set SUPABASE_URL=http://localhost:54321 and use the service_role key from
    the supabase start output.

    Returns:
        Supabase Client instance, or None if configuration is missing
    """
    if not SUPABASE_AVAILABLE:
        logger.error(
            "❌ Supabase client not installed. Install with: pip install supabase"
        )
        return None

    supabase_url = os.getenv("SUPABASE_URL")
    # Support both modern and legacy naming
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
        "SUPABASE_SECRET_KEY"
    )

    if not supabase_url or not supabase_key:
        logger.error(
            "❌ Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY "
            "(or SUPABASE_SECRET_KEY) environment variables to use Supabase database."
        )
        return None

    try:
        client = create_client(supabase_url, supabase_key)
        logger.debug("✅ Supabase client created successfully")
        return client
    except Exception as e:
        logger.error(f"❌ Error creating Supabase client: {e}", exc_info=True)
        return None


def _get_db_connection_string() -> str | None:
    """
    Get the PostgreSQL connection string from environment variables.

    **Simple Explanation:**
    This helper function extracts the database connection string from environment
    variables. It supports both SUPABASE_DB_URL (full connection string) and
    SUPABASE_URL + SUPABASE_DB_PASSWORD (constructs the connection string).

    Returns:
        PostgreSQL connection string, or None if configuration is missing
    """
    # Try to get connection string from environment first
    db_url = os.getenv("SUPABASE_DB_URL")

    if not db_url:
        # Construct connection string from Supabase URL and password
        supabase_url = os.getenv("SUPABASE_URL")
        db_password = os.getenv("SUPABASE_DB_PASSWORD")

        if not supabase_url or not db_password:
            logger.error(
                "❌ Supabase database connection not configured. "
                "Set either SUPABASE_DB_URL (full connection string) or "
                "both SUPABASE_URL and SUPABASE_DB_PASSWORD environment variables."
            )
            return None

        # Extract project reference from Supabase URL
        # Format: https://xxxxx.supabase.co -> xxxxx
        try:
            # Remove https:// and .supabase.co
            project_ref = (
                supabase_url.replace("https://", "")
                .replace(".supabase.co", "")
                .replace("http://", "")
                .replace(":54321", "")
                .split("/")[0]
            )

            # Construct PostgreSQL connection string
            # Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
            # Note: For Supabase cloud, SSL is required. For local Supabase, SSL is disabled.
            if "localhost" in project_ref or "127.0.0.1" in project_ref:
                # Local Supabase - SSL disabled
                db_url = f"postgresql://postgres:{db_password}@localhost:54322/postgres?sslmode=disable"
            else:
                # Production Supabase - SSL required (default)
                db_url = f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
        except Exception as e:
            logger.error(
                f"❌ Error constructing Supabase database connection string: {e}"
            )
            return None

    return db_url


def get_postgres_checkpointer():
    """
    Get a LangGraph Postgres checkpointer using the existing Supabase connection.

    **Simple Explanation:**
    This creates a SYNC checkpointer that stores workflow state in Supabase (PostgreSQL).
    This allows workflows to persist across server restarts and work in multi-instance
    deployments (like Fly.io with multiple machines).

    **Note:** For async workflows, use `get_async_postgres_checkpointer()` instead.

    **Environment Variables:**
    Uses the same Supabase configuration as other database functions:
    - SUPABASE_URL: Your Supabase project URL
    - SUPABASE_SERVICE_ROLE_KEY: Service role key (or SUPABASE_SECRET_KEY)
    - SUPABASE_DB_PASSWORD: Database password for direct PostgreSQL connection
      (optional - can also use connection string via SUPABASE_DB_URL)

    **Alternative:**
    You can also set SUPABASE_DB_URL directly with a full PostgreSQL connection string:
    - Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres

    Returns:
        LangGraph PostgresSaver checkpointer instance, or None if configuration is missing
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError:
        logger.error(
            "❌ LangGraph PostgresSaver or psycopg not available. "
            "Install with: pip install langgraph[postgres] psycopg[binary]"
        )
        return None

    db_url = _get_db_connection_string()
    if not db_url:
        return None

    try:
        # Create PostgresSaver with connection string
        # Simple Explanation: PostgresSaver stores workflow checkpoints in PostgreSQL
        # The tables should already exist from the migration, but we call setup()
        # as a safety net to ensure they're created if the migration hasn't run yet
        checkpointer = PostgresSaver.from_conn_string(db_url)

        # Setup tables if they don't exist (safety net - migration should handle this)
        # Simple Explanation: setup() creates the necessary tables. We call it once
        # as a safety net, but the migration file should have already created them.
        try:
            checkpointer.setup()
            logger.debug("✅ Postgres checkpointer tables verified/created")
        except Exception as setup_error:
            # If setup fails, it might be because tables already exist (from migration)
            # or there's a real error. Log it but don't fail - the checkpointer might still work.
            logger.debug(
                f"⚠️ Postgres checkpointer setup warning (tables may already exist): {setup_error}"
            )

        logger.debug("✅ Postgres checkpointer created successfully")
        return checkpointer
    except Exception as e:
        logger.error(f"❌ Error creating Postgres checkpointer: {e}", exc_info=True)
        return None


async def get_async_postgres_checkpointer():
    """
    Get an async LangGraph Postgres checkpointer using the existing Supabase connection.

    **Simple Explanation:**
    This creates an ASYNC checkpointer that stores workflow state in Supabase (PostgreSQL).
    This is the correct checkpointer to use for async workflows (like BotCallWorkflow).

    **Important:** AsyncPostgresSaver.from_conn_string() returns an async context manager.
    This function returns the context manager itself. You need to enter it (using `async with`)
    before using it. The entered checkpointer should be kept alive for the application lifetime.

    **Environment Variables:**
    Uses the same Supabase configuration as other database functions:
    - SUPABASE_URL: Your Supabase project URL
    - SUPABASE_SERVICE_ROLE_KEY: Service role key (or SUPABASE_SECRET_KEY)
    - SUPABASE_DB_PASSWORD: Database password for direct PostgreSQL connection
      (optional - can also use connection string via SUPABASE_DB_URL)

    **Alternative:**
    You can also set SUPABASE_DB_URL directly with a full PostgreSQL connection string:
    - Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres

    Returns:
        AsyncPostgresSaver context manager (needs to be entered with `async with`),
        or None if configuration is missing

    Example:
        ```python
        checkpointer_cm = await get_async_postgres_checkpointer()
        if checkpointer_cm:
            async with checkpointer_cm as checkpointer:
                # Use checkpointer here - keep it alive for app lifetime
                graph = builder.compile(checkpointer=checkpointer)
        ```
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:
        logger.error(
            "❌ LangGraph AsyncPostgresSaver or psycopg not available. "
            "Install with: pip install langgraph[postgres] psycopg[binary,pool]"
        )
        return None

    db_url = _get_db_connection_string()
    if not db_url:
        return None

    try:
        # Create AsyncPostgresSaver context manager with connection string
        # Simple Explanation: AsyncPostgresSaver.from_conn_string() returns an async
        # context manager. We need to enter it (using `async with`) to get the actual
        # checkpointer. The entered checkpointer should be kept alive for the app lifetime.
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(db_url)

        logger.debug("✅ Async Postgres checkpointer context manager created")
        return checkpointer_cm
    except Exception as e:
        logger.error(
            f"❌ Error creating Async Postgres checkpointer: {e}", exc_info=True
        )
        return None


def save_session_data(room_name: str, session_data: Dict[str, Any]) -> bool:
    """
    Save session data for a room to Supabase with field-level encryption.

    If data already exists for this room, it will be updated (upsert).

    Args:
        room_name: The room identifier (e.g., "abc123") - unencrypted
        session_data: Dictionary containing session information

    Returns:
        True if saved successfully, False otherwise
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot save to Supabase: client not available")
        return False

    try:
        # Encrypt sensitive fields before saving
        encrypted_data = encrypt_sensitive_data(session_data)

        # Prepare data for Supabase insert/update
        # Map session_data keys to database columns
        db_data = {
            "room_name": room_name,
            "session_id": encrypted_data.get("session_id"),
            "workflow_thread_id": encrypted_data.get("workflow_thread_id"),
            "meeting_status": encrypted_data.get("meeting_status", "in_progress"),
            "meeting_start_time": encrypted_data.get("meeting_start_time"),
            "meeting_end_time": encrypted_data.get("meeting_end_time"),
            "interview_type": encrypted_data.get("interview_type"),
            "difficulty_level": encrypted_data.get("difficulty_level"),
            "position": encrypted_data.get("position"),
            "bot_enabled": encrypted_data.get("bot_enabled", False),
            "waiting_for_meeting_ended": encrypted_data.get(
                "waiting_for_meeting_ended", False
            ),
            "waiting_for_transcript_webhook": encrypted_data.get(
                "waiting_for_transcript_webhook", False
            ),
            "transcript_processed": encrypted_data.get("transcript_processed", False),
            "transcript_processing": encrypted_data.get("transcript_processing", False),
            "email_sent": encrypted_data.get("email_sent", False),
            "workflow_paused": encrypted_data.get("workflow_paused", False),
            # Encrypted fields
            "webhook_callback_url": encrypted_data.get("webhook_callback_url"),
            "email_results_to": encrypted_data.get("email_results_to"),
            "candidate_name": encrypted_data.get("candidate_name"),
            "candidate_email": encrypted_data.get("candidate_email"),
            "interviewer_context": encrypted_data.get("interviewer_context"),
            "analysis_prompt": encrypted_data.get("analysis_prompt"),
            "summary_format_prompt": encrypted_data.get("summary_format_prompt"),
            "transcript_text": encrypted_data.get("transcript_text"),
            "candidate_summary": encrypted_data.get("candidate_summary"),
            # processing_status_by_key stores processing status per workflow_thread_id or room_name
            # This allows rooms to be reused without conflicts
            "processing_status_by_key": encrypted_data.get("processing_status_by_key"),
        }

        # Remove None values to avoid overwriting with NULL
        db_data = {k: v for k, v in db_data.items() if v is not None}

        # Use upsert (insert or update) - Supabase handles this with ON CONFLICT
        client.table("rooms").upsert(db_data, on_conflict="room_name").execute()

        logger.info(
            f"✅ Session data saved to Supabase for room: {room_name} (sensitive fields encrypted)"
        )
        return True

    except Exception as e:
        logger.error(
            f"❌ Error saving session data to Supabase for {room_name}: {e}",
            exc_info=True,
        )
        return False


def get_session_data(room_name: str) -> Dict[str, Any] | None:
    """
    Retrieve session data for a room from Supabase and decrypt sensitive fields.

    Args:
        room_name: The room identifier (e.g., "abc123")

    Returns:
        Dictionary with session data (sensitive fields decrypted), or None if not found
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot read from Supabase: client not available")
        return None

    try:
        response = (
            client.table("rooms").select("*").eq("room_name", room_name).execute()
        )

        if not response.data or len(response.data) == 0:
            logger.warning(f"⚠️ No session data found in Supabase for room: {room_name}")
            return None

        # Get the first (and should be only) row
        row = response.data[0]

        # Convert database row back to session_data format
        session_data = {
            "session_id": row.get("session_id"),
            "workflow_thread_id": row.get("workflow_thread_id"),
            "meeting_status": row.get("meeting_status"),
            "meeting_start_time": row.get("meeting_start_time"),
            "meeting_end_time": row.get("meeting_end_time"),
            "interview_type": row.get("interview_type"),
            "difficulty_level": row.get("difficulty_level"),
            "position": row.get("position"),
            "bot_enabled": row.get("bot_enabled"),
            "waiting_for_meeting_ended": row.get("waiting_for_meeting_ended"),
            "waiting_for_transcript_webhook": row.get("waiting_for_transcript_webhook"),
            "transcript_processed": row.get("transcript_processed"),
            "transcript_processing": row.get("transcript_processing"),
            "email_sent": row.get("email_sent"),
            "workflow_paused": row.get("workflow_paused"),
            # Encrypted fields (will be decrypted below)
            "webhook_callback_url": row.get("webhook_callback_url"),
            "email_results_to": row.get("email_results_to"),
            "candidate_name": row.get("candidate_name"),
            "candidate_email": row.get("candidate_email"),
            "interviewer_context": row.get("interviewer_context"),
            "analysis_prompt": row.get("analysis_prompt"),
            "summary_format_prompt": row.get("summary_format_prompt"),
            "transcript_text": row.get("transcript_text"),
            "candidate_summary": row.get("candidate_summary"),
            # processing_status_by_key stores processing status per workflow_thread_id or room_name
            "processing_status_by_key": row.get("processing_status_by_key"),
        }

        # Remove None values
        session_data = {k: v for k, v in session_data.items() if v is not None}

        # Decrypt sensitive fields
        decrypted_data = decrypt_sensitive_data(session_data)

        logger.info(
            f"✅ Retrieved session data from Supabase for room: {room_name} (sensitive fields decrypted)"
        )
        return decrypted_data

    except Exception as e:
        logger.error(
            f"❌ Error retrieving session data from Supabase for {room_name}: {e}",
            exc_info=True,
        )
        return None


def delete_session_data(room_name: str) -> bool:
    """
    Delete session data for a room from Supabase (optional cleanup).

    Args:
        room_name: The room identifier (e.g., "abc123")

    Returns:
        True if deleted successfully, False otherwise
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot delete from Supabase: client not available")
        return False

    try:
        response = client.table("rooms").delete().eq("room_name", room_name).execute()

        # Check if any rows were deleted
        if response.data and len(response.data) > 0:
            logger.info(f"✅ Session data deleted from Supabase for room: {room_name}")
            return True
        else:
            logger.warning(
                f"⚠️ No session data to delete from Supabase for room: {room_name}"
            )
            return False

    except Exception as e:
        logger.error(
            f"❌ Error deleting session data from Supabase for {room_name}: {e}",
            exc_info=True,
        )
        return False


def save_bot_session(bot_id: str, bot_session_data: Dict[str, Any]) -> bool:
    """
    Save or update bot session data in Supabase.

    **Simple Explanation:**
    This function saves bot session information to the database. It stores:
    - Bot status (running, completed, failed)
    - Room information
    - Bot configuration
    - Transcript, Q&A pairs, and insights (when available)
    - Timestamps

    Args:
        bot_id: Unique bot session identifier (UUID)
        bot_session_data: Dictionary containing bot session information:
            - room_url: Full Daily.co room URL
            - room_name: Room name
            - status: Bot status ('running', 'completed', 'failed')
            - started_at: ISO timestamp when bot started
            - completed_at: ISO timestamp when bot completed (optional)
            - process_insights: Whether to process insights
            - bot_config: Bot configuration dictionary
            - transcript_text: Full transcript (optional, will be encrypted)
            - qa_pairs: List of Q&A pairs (optional)
            - insights: Insights dictionary (optional)
            - error: Error message if failed (optional)

    Returns:
        True if saved successfully, False otherwise
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot save bot session to Supabase: client not available")
        return False

    try:
        # Encrypt transcript_text if present (it's a sensitive field)
        db_data = bot_session_data.copy()
        if "transcript_text" in db_data and db_data["transcript_text"]:
            db_data["transcript_text"] = encrypt_field(db_data["transcript_text"])

        # Prepare data for Supabase
        # Convert ISO timestamps to proper format if they're strings
        if "started_at" in db_data and isinstance(db_data["started_at"], str):
            # Remove 'Z' suffix if present, Supabase handles timezone
            db_data["started_at"] = db_data["started_at"].rstrip("Z")
        if "completed_at" in db_data and isinstance(db_data["completed_at"], str):
            db_data["completed_at"] = db_data["completed_at"].rstrip("Z")

        # Use upsert (insert or update) based on bot_id
        client.table("bot_sessions").upsert(
            {"bot_id": bot_id, **db_data}, on_conflict="bot_id"
        ).execute()

        logger.info(f"✅ Bot session saved to Supabase: bot_id={bot_id}")
        return True

    except Exception as e:
        logger.error(
            f"❌ Error saving bot session to Supabase for {bot_id}: {e}",
            exc_info=True,
        )
        return False


def get_bot_session(bot_id: str) -> Dict[str, Any] | None:
    """
    Retrieve bot session data from Supabase.

    **Simple Explanation:**
    This function retrieves bot session information from the database.
    It decrypts the transcript_text field automatically.

    Args:
        bot_id: Unique bot session identifier (UUID)

    Returns:
        Dictionary with bot session data (transcript_text decrypted), or None if not found
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot read bot session from Supabase: client not available")
        return None

    try:
        response = (
            client.table("bot_sessions").select("*").eq("bot_id", bot_id).execute()
        )

        if not response.data or len(response.data) == 0:
            logger.warning(f"⚠️ No bot session found in Supabase for bot_id: {bot_id}")
            return None

        # Get the first (and should be only) row
        row = response.data[0]

        # Convert database row to dictionary
        bot_session = {
            "bot_id": row.get("bot_id"),
            "room_url": row.get("room_url"),
            "room_name": row.get("room_name"),
            "status": row.get("status"),
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "process_insights": row.get("process_insights"),
            "bot_config": row.get("bot_config"),
            "transcript_text": row.get("transcript_text"),
            "qa_pairs": row.get("qa_pairs"),
            "insights": row.get("insights"),
            "error": row.get("error"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

        # Decrypt transcript_text if present
        if bot_session.get("transcript_text"):
            try:
                bot_session["transcript_text"] = decrypt_field(
                    bot_session["transcript_text"]
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ Could not decrypt transcript_text for bot_id {bot_id}: {e}"
                )
                # If decryption fails, try to use as-is (might be unencrypted for migration)
                pass

        # Format timestamps as ISO strings with Z suffix for API responses
        if bot_session.get("started_at"):
            started_at = bot_session["started_at"]
            if isinstance(started_at, str) and not started_at.endswith("Z"):
                bot_session["started_at"] = started_at + "Z"
        if bot_session.get("completed_at"):
            completed_at = bot_session["completed_at"]
            if isinstance(completed_at, str) and not completed_at.endswith("Z"):
                bot_session["completed_at"] = completed_at + "Z"

        logger.info(
            f"✅ Retrieved bot session from Supabase: bot_id={bot_id} (transcript_text decrypted)"
        )
        return bot_session

    except Exception as e:
        logger.error(
            f"❌ Error retrieving bot session from Supabase for {bot_id}: {e}",
            exc_info=True,
        )
        return None


def get_bot_session_by_room_name(room_name: str) -> Dict[str, Any] | None:
    """
    Retrieve bot session data by room_name (most recent session for that room).

    **Simple Explanation:**
    This function finds the most recent bot session for a given room name.
    Useful when you have a room_name but need to find the associated bot_id.

    Args:
        room_name: Room name to search for

    Returns:
        Dictionary with bot session data, or None if not found
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot read bot session from Supabase: client not available")
        return None

    try:
        response = (
            client.table("bot_sessions")
            .select("*")
            .eq("room_name", room_name)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            logger.warning(
                f"⚠️ No bot session found in Supabase for room_name: {room_name}"
            )
            return None

        # Get the first (most recent) row
        row = response.data[0]

        # Convert and decrypt (same as get_bot_session)
        bot_session = {
            "bot_id": row.get("bot_id"),
            "room_url": row.get("room_url"),
            "room_name": row.get("room_name"),
            "status": row.get("status"),
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "process_insights": row.get("process_insights"),
            "bot_config": row.get("bot_config"),
            "transcript_text": row.get("transcript_text"),
            "qa_pairs": row.get("qa_pairs"),
            "insights": row.get("insights"),
            "error": row.get("error"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

        # Decrypt transcript_text if present
        if bot_session.get("transcript_text"):
            try:
                bot_session["transcript_text"] = decrypt_field(
                    bot_session["transcript_text"]
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ Could not decrypt transcript_text for room_name {room_name}: {e}"
                )
                pass

        # Format timestamps
        if bot_session.get("started_at"):
            started_at = bot_session["started_at"]
            if isinstance(started_at, str) and not started_at.endswith("Z"):
                bot_session["started_at"] = started_at + "Z"
        if bot_session.get("completed_at"):
            completed_at = bot_session["completed_at"]
            if isinstance(completed_at, str) and not completed_at.endswith("Z"):
                bot_session["completed_at"] = completed_at + "Z"

        return bot_session

    except Exception as e:
        logger.error(
            f"❌ Error retrieving bot session by room_name from Supabase for {room_name}: {e}",
            exc_info=True,
        )
        return None


def save_workflow_thread_data(
    workflow_thread_id: str, thread_data: Dict[str, Any]
) -> bool:
    """
    Save workflow thread data to Supabase with field-level encryption.

    **Simple Explanation:**
    This function saves all data for a workflow run, keyed by workflow_thread_id.
    This allows rooms to be reused - each workflow run gets its own row in the database.

    The workflow_thread_id is the primary key, so multiple workflow runs can use
    the same room_name without conflicts.

    Args:
        workflow_thread_id: Unique workflow thread identifier (UUID string)
        thread_data: Dictionary containing workflow thread information:
            - room_name: Room name this workflow is using
            - room_url: Full Daily.co room URL
            - candidate_name, candidate_email: User/candidate info (encrypted)
            - transcript_text: Transcript (encrypted)
            - transcript_processed, email_sent, webhook_sent: Processing state
            - candidate_summary: Summary (encrypted)
            - checkpoint_id: LangGraph checkpoint ID for resuming workflows (not encrypted)
            - And all other workflow-related fields

    Returns:
        True if saved successfully, False otherwise
    """
    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot save workflow thread to Supabase: client not available")
        return False

    try:
        # Encrypt sensitive fields before saving
        encrypted_data = encrypt_sensitive_data(thread_data)

        # Prepare data for Supabase insert/update
        # Map thread_data keys to database columns
        db_data = {
            "workflow_thread_id": workflow_thread_id,
            "room_name": encrypted_data.get("room_name"),
            "room_url": encrypted_data.get("room_url"),
            "room_id": encrypted_data.get("room_id"),
            "session_id": encrypted_data.get("session_id"),
            "candidate_name": encrypted_data.get("candidate_name"),
            "candidate_email": encrypted_data.get("candidate_email"),
            "interview_type": encrypted_data.get("interview_type"),
            "position": encrypted_data.get("position"),
            "difficulty_level": encrypted_data.get("difficulty_level"),
            "interviewer_context": encrypted_data.get("interviewer_context"),
            "analysis_prompt": encrypted_data.get("analysis_prompt"),
            "summary_format_prompt": encrypted_data.get("summary_format_prompt"),
            "bot_enabled": encrypted_data.get("bot_enabled", False),
            "bot_id": encrypted_data.get("bot_id"),
            "bot_config": encrypted_data.get("bot_config"),
            "meeting_status": encrypted_data.get("meeting_status", "in_progress"),
            "meeting_start_time": encrypted_data.get("meeting_start_time"),
            "meeting_end_time": encrypted_data.get("meeting_end_time"),
            "duration": encrypted_data.get("duration"),
            "transcript_text": encrypted_data.get("transcript_text"),
            "transcript_id": encrypted_data.get("transcript_id"),
            "transcript_processed": encrypted_data.get("transcript_processed", False),
            "transcript_processing": encrypted_data.get("transcript_processing", False),
            "email_sent": encrypted_data.get("email_sent", False),
            "webhook_sent": encrypted_data.get("webhook_sent", False),
            "candidate_summary": encrypted_data.get("candidate_summary"),
            "insights": encrypted_data.get("insights"),
            "qa_pairs": encrypted_data.get("qa_pairs"),
            "webhook_callback_url": encrypted_data.get("webhook_callback_url"),
            "email_results_to": encrypted_data.get("email_results_to"),
            "workflow_paused": encrypted_data.get("workflow_paused", False),
            "waiting_for_meeting_ended": encrypted_data.get(
                "waiting_for_meeting_ended", False
            ),
            "waiting_for_transcript_webhook": encrypted_data.get(
                "waiting_for_transcript_webhook", False
            ),
            "metadata": encrypted_data.get("metadata"),
            # checkpoint_id is an operational field (not sensitive), so get it directly from thread_data
            "checkpoint_id": thread_data.get("checkpoint_id"),
            # usage_stats is an operational field (not sensitive), so get it directly from thread_data
            "usage_stats": thread_data.get("usage_stats"),
            # unkey_key_id is an operational field (not sensitive), so get it directly from thread_data
            "unkey_key_id": thread_data.get("unkey_key_id"),
            # bot timing fields are operational (not sensitive), so get them directly from thread_data
            "bot_join_time": thread_data.get("bot_join_time"),
            "bot_leave_time": thread_data.get("bot_leave_time"),
            "bot_duration": thread_data.get("bot_duration"),
        }

        # Remove None values to avoid overwriting with NULL
        db_data = {k: v for k, v in db_data.items() if v is not None}

        # Use upsert (insert or update) - Supabase handles this with ON CONFLICT
        client.table("workflow_threads").upsert(
            db_data, on_conflict="workflow_thread_id"
        ).execute()

        logger.info(
            f"✅ Workflow thread data saved to Supabase: workflow_thread_id={workflow_thread_id} (sensitive fields encrypted)"
        )
        return True

    except Exception as e:
        logger.error(
            f"❌ Error saving workflow thread data to Supabase for {workflow_thread_id}: {e}",
            exc_info=True,
        )
        return False


def get_workflow_thread_data(workflow_thread_id: str) -> Dict[str, Any] | None:
    """
    Retrieve workflow thread data from Supabase and decrypt sensitive fields.

    **Simple Explanation:**
    This function retrieves all data for a specific workflow run by its workflow_thread_id.
    This is the primary way to get workflow data - each workflow run has its own row.

    Args:
        workflow_thread_id: Unique workflow thread identifier (UUID string)

    Returns:
        Dictionary with workflow thread data (sensitive fields decrypted), or None if not found
    """
    client = get_supabase_client()
    if not client:
        logger.error(
            "❌ Cannot read workflow thread from Supabase: client not available"
        )
        return None

    try:
        response = (
            client.table("workflow_threads")
            .select("*")
            .eq("workflow_thread_id", workflow_thread_id)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            logger.warning(
                f"⚠️ No workflow thread data found in Supabase for workflow_thread_id: {workflow_thread_id}"
            )
            return None

        # Get the first (and should be only) row
        row = response.data[0]

        # Convert database row back to thread_data format
        thread_data = {
            "workflow_thread_id": row.get("workflow_thread_id"),
            "room_name": row.get("room_name"),
            "room_url": row.get("room_url"),
            "room_id": row.get("room_id"),
            "session_id": row.get("session_id"),
            "candidate_name": row.get("candidate_name"),
            "candidate_email": row.get("candidate_email"),
            "interview_type": row.get("interview_type"),
            "position": row.get("position"),
            "difficulty_level": row.get("difficulty_level"),
            "interviewer_context": row.get("interviewer_context"),
            "analysis_prompt": row.get("analysis_prompt"),
            "summary_format_prompt": row.get("summary_format_prompt"),
            "bot_enabled": row.get("bot_enabled"),
            "bot_id": row.get("bot_id"),
            "bot_config": row.get("bot_config"),
            "meeting_status": row.get("meeting_status"),
            "meeting_start_time": row.get("meeting_start_time"),
            "meeting_end_time": row.get("meeting_end_time"),
            "duration": row.get("duration"),
            "transcript_text": row.get("transcript_text"),
            "transcript_id": row.get("transcript_id"),
            "transcript_processed": row.get("transcript_processed"),
            "transcript_processing": row.get("transcript_processing"),
            "email_sent": row.get("email_sent"),
            "webhook_sent": row.get("webhook_sent"),
            "candidate_summary": row.get("candidate_summary"),
            "insights": row.get("insights"),
            "qa_pairs": row.get("qa_pairs"),
            "webhook_callback_url": row.get("webhook_callback_url"),
            "email_results_to": row.get("email_results_to"),
            "workflow_paused": row.get("workflow_paused"),
            "waiting_for_meeting_ended": row.get("waiting_for_meeting_ended"),
            "waiting_for_transcript_webhook": row.get("waiting_for_transcript_webhook"),
            "metadata": row.get("metadata"),
            # checkpoint_id is an operational field (not sensitive), so include it directly
            "checkpoint_id": row.get("checkpoint_id"),
            # usage_stats is an operational field (not sensitive), so include it directly
            "usage_stats": row.get("usage_stats"),
            # unkey_key_id is an operational field (not sensitive), so include it directly
            "unkey_key_id": row.get("unkey_key_id"),
            # bot timing fields are operational (not sensitive), so include them directly
            "bot_join_time": row.get("bot_join_time"),
            "bot_leave_time": row.get("bot_leave_time"),
            "bot_duration": row.get("bot_duration"),
        }

        # Remove None values
        thread_data = {k: v for k, v in thread_data.items() if v is not None}

        # Decrypt sensitive fields
        decrypted_data = decrypt_sensitive_data(thread_data)

        logger.info(
            f"✅ Retrieved workflow thread data from Supabase: workflow_thread_id={workflow_thread_id} (sensitive fields decrypted)"
        )
        return decrypted_data

    except Exception as e:
        logger.error(
            f"❌ Error retrieving workflow thread data from Supabase for {workflow_thread_id}: {e}",
            exc_info=True,
        )
        return None


def get_workflow_threads_by_room_name(room_name: str) -> list[Dict[str, Any]]:
    """
    Get all workflow threads for a given room_name.

    **Simple Explanation:**
    This function retrieves all workflow runs that used a specific room.
    Useful for finding all workflow threads associated with a room, since
    rooms can be reused across multiple workflow runs.

    Args:
        room_name: Room name to search for

    Returns:
        List of workflow thread data dictionaries (sensitive fields decrypted), empty list if none found
    """
    client = get_supabase_client()
    if not client:
        logger.error(
            "❌ Cannot read workflow threads from Supabase: client not available"
        )
        return []

    try:
        response = (
            client.table("workflow_threads")
            .select("*")
            .eq("room_name", room_name)
            .order("created_at", desc=True)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            logger.debug(
                f"No workflow threads found in Supabase for room_name: {room_name}"
            )
            return []

        # Convert all rows and decrypt sensitive fields
        threads = []
        for row in response.data:
            thread_data = {
                "workflow_thread_id": row.get("workflow_thread_id"),
                "room_name": row.get("room_name"),
                "room_url": row.get("room_url"),
                "room_id": row.get("room_id"),
                "session_id": row.get("session_id"),
                "candidate_name": row.get("candidate_name"),
                "candidate_email": row.get("candidate_email"),
                "interview_type": row.get("interview_type"),
                "position": row.get("position"),
                "difficulty_level": row.get("difficulty_level"),
                "interviewer_context": row.get("interviewer_context"),
                "analysis_prompt": row.get("analysis_prompt"),
                "summary_format_prompt": row.get("summary_format_prompt"),
                "bot_enabled": row.get("bot_enabled"),
                "bot_id": row.get("bot_id"),
                "bot_config": row.get("bot_config"),
                "meeting_status": row.get("meeting_status"),
                "meeting_start_time": row.get("meeting_start_time"),
                "meeting_end_time": row.get("meeting_end_time"),
                "duration": row.get("duration"),
                "transcript_text": row.get("transcript_text"),
                "transcript_id": row.get("transcript_id"),
                "transcript_processed": row.get("transcript_processed"),
                "transcript_processing": row.get("transcript_processing"),
                "email_sent": row.get("email_sent"),
                "webhook_sent": row.get("webhook_sent"),
                "candidate_summary": row.get("candidate_summary"),
                "insights": row.get("insights"),
                "qa_pairs": row.get("qa_pairs"),
                "webhook_callback_url": row.get("webhook_callback_url"),
                "email_results_to": row.get("email_results_to"),
                "workflow_paused": row.get("workflow_paused"),
                "waiting_for_meeting_ended": row.get("waiting_for_meeting_ended"),
                "waiting_for_transcript_webhook": row.get(
                    "waiting_for_transcript_webhook"
                ),
                "metadata": row.get("metadata"),
                # checkpoint_id is an operational field (not sensitive), so include it directly
                "checkpoint_id": row.get("checkpoint_id"),
                # usage_stats is an operational field (not sensitive), so include it directly
                "usage_stats": row.get("usage_stats"),
            }

            # Remove None values
            thread_data = {k: v for k, v in thread_data.items() if v is not None}

            # Decrypt sensitive fields
            decrypted_data = decrypt_sensitive_data(thread_data)
            threads.append(decrypted_data)

        logger.info(
            f"✅ Retrieved {len(threads)} workflow thread(s) from Supabase for room_name: {room_name}"
        )
        return threads

    except Exception as e:
        logger.error(
            f"❌ Error retrieving workflow threads by room_name from Supabase for {room_name}: {e}",
            exc_info=True,
        )
        return []


def increment_workflow_usage_cost(
    workflow_thread_id: str, cost_usd: float, posthog_trace_id: str | None = None
) -> bool:
    """
    Increment the total cost for a workflow thread.

    **Simple Explanation:**
    This is a convenience function that adds a cost amount to the existing total
    cost stored in the workflow_threads.usage_stats JSONB column. It reads the
    current value, adds the new cost, and saves it back.

    This is a lower-level helper - for most use cases, use the function in
    flow.utils.usage_tracking instead, which provides better error handling.

    Args:
        workflow_thread_id: Unique identifier for the workflow run
        cost_usd: Cost in USD to add to the total
        posthog_trace_id: Optional PostHog trace ID to store for correlation

    Returns:
        True if updated successfully, False otherwise
    """
    if not workflow_thread_id:
        logger.warning("⚠️ Cannot increment usage cost: workflow_thread_id is required")
        return False

    try:
        # Get current workflow thread data
        thread_data = get_workflow_thread_data(workflow_thread_id)
        if not thread_data:
            logger.warning(
                f"⚠️ Workflow thread not found: {workflow_thread_id} - cannot increment usage cost"
            )
            return False

        # Get current usage_stats or initialize
        usage_stats = thread_data.get("usage_stats") or {}
        if not usage_stats:
            usage_stats = {
                "total_cost_usd": 0.0,
                "posthog_trace_id": None,
            }

        # Increment total cost
        current_total = usage_stats.get("total_cost_usd", 0.0)
        usage_stats["total_cost_usd"] = current_total + cost_usd

        # Update posthog_trace_id if provided
        if posthog_trace_id:
            usage_stats["posthog_trace_id"] = posthog_trace_id

        # Save updated data
        thread_data["usage_stats"] = usage_stats
        return save_workflow_thread_data(workflow_thread_id, thread_data)

    except Exception as e:
        logger.error(
            f"❌ Error incrementing usage cost for {workflow_thread_id}: {e}",
            exc_info=True,
        )
        return False


def get_user_id_from_unkey_key_id(unkey_key_id: str) -> str | None:
    """
    Get user ID from unkey_key_id by querying public.users table.

    **Simple Explanation:**
    This function looks up a user in the public.users table by searching for
    the unkeyId column.

    Args:
        unkey_key_id: The Unkey key identifier to look up

    Returns:
        User ID (UUID string) if found, None otherwise
    """
    if not unkey_key_id:
        logger.warning("⚠️ Cannot lookup user: unkey_key_id is required")
        return None

    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot lookup user: Supabase client not available")
        return None

    try:
        response = (
            client.table("users")
            .select("id")
            .eq("unkeyId", unkey_key_id)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            user_id = str(response.data[0]["id"])
            logger.debug(f"✅ Found user_id {user_id} for unkey_key_id {unkey_key_id}")
            return user_id

        logger.warning(f"⚠️ No user found for unkey_key_id: {unkey_key_id}")
        return None

    except Exception as e:
        logger.error(
            f"❌ Error looking up user by unkey_key_id {unkey_key_id}: {e}",
            exc_info=True,
        )
        return None


def get_user_balance(user_id: str) -> float:
    """
    Get current balance for a user.

    **Simple Explanation:**
    This function retrieves the current balance from the users table.
    The balance field should already exist in the users table.
    Tries public.users first, then auth.users if not found.

    Args:
        user_id: User ID (UUID string)

    Returns:
        Current balance as float, default 0.0 if not found or error
    """
    if not user_id:
        logger.warning("⚠️ Cannot get balance: user_id is required")
        return 0.0

    client = get_supabase_client()
    if not client:
        logger.error("❌ Cannot get balance: Supabase client not available")
        return 0.0

    try:
        # Try public.users first (since usage_transactions references it)
        response = (
            client.table("users").select("credit_balance").eq("id", user_id).execute()
        )

        if response.data and len(response.data) > 0:
            balance = response.data[0].get("credit_balance")
            if balance is not None:
                return float(balance)
            return 0.0

        # If not found in public.users, try auth.users using raw SQL
        db_url = _get_db_connection_string()
        if db_url:
            try:
                import psycopg

                with psycopg.connect(db_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT credit_balance FROM auth.users WHERE id = %s LIMIT 1",
                            (user_id,),
                        )
                        row = cur.fetchone()
                        if row and row[0] is not None:
                            return float(row[0])
            except ImportError:
                pass  # psycopg not available, continue
            except Exception:
                pass  # Error querying auth.users, continue

        logger.warning(f"⚠️ User not found for balance lookup: {user_id}")
        return 0.0

    except Exception as e:
        logger.error(
            f"❌ Error getting balance for user {user_id}: {e}",
            exc_info=True,
        )
        return 0.0


def create_usage_transaction(
    workflow_thread_id: str,
    amount_usd: float,
    duration_seconds: int | None = None,
    lpl_cost: float | None = None,
) -> bool:
    """
    Create a usage transaction and deduct balance when workflow completes.

    **Simple Explanation:**
    This function creates a transaction record in the usage_transactions table
    and deducts the amount from the user's balance. It looks up the user via
    unkey_key_id stored in the workflow_threads table.

    Args:
        workflow_thread_id: Unique workflow thread identifier
        amount_usd: Amount to deduct (positive value, will be stored as negative)
                   This is the customer cost (what they're charged)
        duration_seconds: Optional duration in seconds for bot usage
        lpl_cost: Optional actual cost incurred by LPL (LLM, STT, etc.) for internal analytics

    Returns:
        True if transaction created successfully, False otherwise
    """
    if not workflow_thread_id:
        logger.warning(
            "⚠️ Cannot create usage transaction: workflow_thread_id is required"
        )
        return False

    if amount_usd <= 0:
        logger.debug(
            f"⏭️ Skipping transaction creation for {workflow_thread_id}: amount is {amount_usd} (non-positive)"
        )
        return False

    client = get_supabase_client()
    if not client:
        logger.error(
            "❌ Cannot create usage transaction: Supabase client not available"
        )
        return False

    try:
        # Get workflow thread data to extract unkey_key_id and duration
        thread_data = get_workflow_thread_data(workflow_thread_id)
        if not thread_data:
            logger.warning(
                f"⚠️ Workflow thread not found: {workflow_thread_id} - cannot create transaction"
            )
            return False

        unkey_key_id = thread_data.get("unkey_key_id")
        if not unkey_key_id:
            logger.warning(
                f"⚠️ No unkey_key_id found for workflow_thread_id {workflow_thread_id} - cannot create transaction"
            )
            return False

        # Get duration from thread_data if not provided
        if duration_seconds is None:
            duration_seconds = thread_data.get("bot_duration") or thread_data.get(
                "duration"
            )

        # Look up user_id from unkey_key_id (returns auth.users.id)
        auth_user_id = get_user_id_from_unkey_key_id(unkey_key_id)
        if not auth_user_id:
            logger.warning(
                f"⚠️ User not found for unkey_key_id {unkey_key_id} - cannot create transaction"
            )
            return False

        # Verify user exists in public.users (since usage_transactions.user_id references it)
        # In most Supabase setups, auth.users.id == public.users.id, but we verify
        user_check = (
            client.table("users").select("id").eq("id", auth_user_id).limit(1).execute()
        )

        if not user_check.data or len(user_check.data) == 0:
            logger.warning(
                f"⚠️ User {auth_user_id} not found in public.users - "
                "cannot create transaction (user may need to be synced)"
            )
            return False

        user_id = auth_user_id  # Use the same ID if it exists in both tables

        # Get current balance
        balance_before = get_user_balance(user_id)
        balance_after = balance_before - amount_usd

        # Check for existing transaction to prevent duplicates
        # Check by user_id, amount, and type within last hour
        from datetime import datetime, timedelta

        one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"

        existing_check = (
            client.table("usage_transactions")
            .select("id")
            .eq("user_id", user_id)
            .eq("amount", -amount_usd)  # Negative amount
            .eq("type", "usage_burn")
            .gte("created_at", one_hour_ago)
            .limit(1)
            .execute()
        )

        if existing_check.data and len(existing_check.data) > 0:
            logger.warning(
                f"⚠️ Duplicate transaction detected for workflow_thread_id {workflow_thread_id} - skipping"
            )
            return False

        # Create transaction record
        transaction_data = {
            "user_id": user_id,
            "amount": -amount_usd,  # Store as negative for deductions
            "type": "usage_burn",
        }

        if duration_seconds is not None:
            transaction_data["duration"] = duration_seconds

        if lpl_cost is not None:
            transaction_data["lpl_cost"] = lpl_cost

        # Insert transaction
        transaction_response = (
            client.table("usage_transactions").insert(transaction_data).execute()
        )

        if not transaction_response.data:
            logger.error(
                f"❌ Failed to create usage transaction for {workflow_thread_id}"
            )
            return False

        # Update user balance
        # Try public.users first (since usage_transactions references it)
        try:
            update_response = (
                client.table("users")
                .update({"credit_balance": balance_after})
                .eq("id", user_id)
                .execute()
            )

            if not update_response.data:
                # If not found in public.users, try auth.users using raw SQL
                db_url = _get_db_connection_string()
                if db_url:
                    try:
                        import psycopg

                        with psycopg.connect(db_url) as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "UPDATE auth.users SET credit_balance = %s WHERE id = %s",
                                    (balance_after, user_id),
                                )
                                conn.commit()
                                if cur.rowcount > 0:
                                    update_response = type(
                                        "obj", (object,), {"data": [{"id": user_id}]}
                                    )()
                    except ImportError:
                        pass  # psycopg not available
                    except Exception as e:
                        logger.warning(f"⚠️ Error updating auth.users balance: {e}")

            if update_response.data:
                lpl_cost_info = (
                    f", lpl_cost=${lpl_cost:.6f}" if lpl_cost is not None else ""
                )
                logger.info(
                    f"✅ Created usage transaction for workflow_thread_id {workflow_thread_id}: "
                    f"user_id={user_id}, amount=${amount_usd:.6f} (customer_cost), "
                    f"balance ${balance_before:.6f} → ${balance_after:.6f}"
                    + (f", duration={duration_seconds}s" if duration_seconds else "")
                    + lpl_cost_info
                )
                return True
            else:
                logger.error(f"❌ Failed to update balance for user {user_id}")
                return False

        except Exception as e:
            logger.error(
                f"❌ Error updating balance for user {user_id}: {e}",
                exc_info=True,
            )
            return False

    except Exception as e:
        logger.error(
            f"❌ Error creating usage transaction for {workflow_thread_id}: {e}",
            exc_info=True,
        )
        return False
