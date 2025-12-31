# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PailFlow FastAPI Application

Main entry point for the PailFlow API server with REST API.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Add project root directory to Python path to allow imports from shared module
# This allows the script to find the 'shared' module in the project root
# Since we're now in flow/, we need to go up one level to reach the project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv  # noqa: E402
from fastapi import (  # noqa: E402
    APIRouter,
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from shared.auth import UnkeyAuthMiddleware  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402


# Setup logging first so we can use logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load .env from flow/ directory
# Simple Explanation: This loads environment variables from .env file in the flow/ directory
env_path = Path(__file__).parent / ".env"  # flow/.env
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"✅ Loaded .env from: {env_path}")
else:
    logger.warning(f"⚠️ .env file not found at: {env_path}")
    # Fallback: try loading from current directory
    load_dotenv()

app = FastAPI(
    title="PailFlow API",
    description="Bot API for joining bots to Daily.co rooms",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(UnkeyAuthMiddleware)


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Add API version header to responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add version header for versioned endpoints
        if request.url.path.startswith("/v1/"):
            response.headers["X-API-Version"] = "v1"
        elif request.url.path.startswith("/v2/"):
            response.headers["X-API-Version"] = "v2"
        else:
            # Unversioned endpoints (except health, webhooks, meet, favicon)
            if not request.url.path.startswith(
                ("/health", "/webhooks", "/meet", "/favicon")
            ):
                response.headers["X-API-Version"] = "unversioned"
                response.headers["X-API-Deprecated"] = "true"

        return response


app.add_middleware(VersionHeaderMiddleware)


# Shared Business Logic


def check_credits_for_request(
    request: Request, required_credits: float = 0.15
) -> tuple[bool, dict[str, Any] | None]:
    """
    Check if the authenticated user has sufficient credits for the request.

    **Simple Explanation:**
    This function checks if the user (identified by unkey_key_id from request state)
    has sufficient credits in their account. It follows the error handling pattern
    from bot_call.py with clear, actionable error messages.

    Args:
        request: FastAPI Request object (contains unkey_key_id in request.state)
        required_credits: Minimum credits required (default: 0.15 for bot calls)

    Returns:
        Tuple of (success: bool, error_response: dict | None)
        - If successful: (True, None)
        - If error: (False, error_response_dict)
    """
    try:
        # Extract unkey_key_id from request state (set by UnkeyAuthMiddleware)
        unkey_key_id = None
        if hasattr(request.state, "unkey_key_id"):
            unkey_key_id = request.state.unkey_key_id

        if not unkey_key_id:
            logger.warning("⚠️ No unkey_key_id in request state - cannot check credits")
            return (
                False,
                {
                    "error": "authentication_error",
                    "detail": "API key authentication failed.",
                    "message": "Please verify your API key or contact support.",
                },
            )

        # Check user credits using database helper
        from flow.db import check_user_credits

        has_credits, current_balance = check_user_credits(
            unkey_key_id, required_credits
        )

        if current_balance is None:
            # User not found in database - could mean:
            # 1. User hasn't added credits yet (exists in auth.users but not in public.users)
            # 2. Invalid/wrong API key
            logger.warning("⚠️ User not found in database")
            return (
                False,
                {
                    "error": "user_not_found",
                    "detail": "You haven't added credits yet, or this is the wrong API key.",
                    "message": "Please add credits to your account or verify your API key.",
                },
            )

        if not has_credits:
            # Insufficient credits
            logger.warning(
                f"⚠️ Insufficient credits: balance={current_balance}, required={required_credits}"
            )
            return (
                False,
                {
                    "error": "insufficient_credits",
                    "detail": "Your account has insufficient credits to perform this action.",
                    "balance": current_balance,
                    "message": "Please add credits to your account to continue.",
                },
            )

        # Success - user has sufficient credits
        logger.debug(
            f"✅ Credit check passed: balance={current_balance}, required={required_credits}"
        )
        return (True, None)

    except Exception as e:
        logger.error(
            f"❌ Error checking credits: {e}",
            exc_info=True,
        )
        return (
            False,
            {
                "error": "credit_check_error",
                "detail": "An error occurred while checking your account credits.",
                "message": "Please try again or contact support if the issue persists.",
            },
        )


# REST API Endpoints


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "pailflow"}


# ============================================================================
# Bot API Router
# ============================================================================
# Simple API for joining bots to existing Daily rooms, transcribing, and processing results

# ============================================================================
# v1 API Router
# ============================================================================
v1_router = APIRouter(
    prefix="/v1",
    tags=["v1"],
    responses={404: {"description": "Not found"}},
)

import uuid  # noqa: E402
from datetime import datetime  # noqa: E402

from flow.steps.agent_call.bot.bot_service import bot_service  # noqa: E402
from flow.db import save_bot_session, get_bot_session  # noqa: E402


# Pydantic models for bot API
class BotConfig(BaseModel):
    """Bot configuration for joining a room."""

    bot_prompt: str
    name: str = "PailBot"
    video_mode: str | None = (
        "animated"  # "static" or "animated" (optional, defaults to "animated")
    )
    static_image: str | None = None  # Only used when video_mode="static"
    bot_greeting: str | None = None  # Optional custom greeting message


class BotJoinRequest(BaseModel):
    """Request to start a bot in an existing room."""

    provider: str = (
        "daily"  # Provider (default: "daily" for future multi-provider support)
    )
    room_url: str  # Full Daily.co room URL
    token: str | None = None  # Optional meeting token
    bot_config: BotConfig
    process_insights: bool = True  # Whether to extract insights after bot finishes

    # Optional: Email and processing configuration
    email: str | None = None  # Email to send results to (renamed from candidate_email)
    analysis_prompt: str | None = None  # Custom prompt for AI analysis
    summary_format_prompt: str | None = None  # Custom prompt for summary formatting
    webhook_callback_url: str | None = None  # Webhook URL to send results to


class BotJoinResponse(BaseModel):
    """Response when starting a bot."""

    status: str
    bot_id: str
    room_url: str


class BotStatusResponse(BaseModel):
    """Response for bot status query."""

    status: str  # "running", "completed", "failed"
    bot_id: str
    room_url: str
    started_at: str | None = None
    completed_at: str | None = None
    transcript: str | None = None
    qa_pairs: list[dict[str, Any]] | None = None
    insights: dict[str, Any] | None = None
    error: str | None = None


@v1_router.post("/api/bot/join", response_model=BotJoinResponse)
async def join_bot_v1(
    request: BotJoinRequest, http_request: Request
) -> BotJoinResponse:
    """
    Start a bot in an existing Daily room using the BotCallWorkflow (v1 API).

    **Simple Explanation:**
    This endpoint starts an AI bot that will join an existing Daily.co video room.
    The bot will:
    1. Join the room and start transcribing the conversation
    2. Have conversations with participants based on the bot_config
    3. When the bot finishes, automatically process the transcript (Q&A parsing, insights, email, webhook)
    4. Store results that can be retrieved via the status endpoint

    **Workflow:**
    This endpoint uses the BotCallWorkflow which orchestrates the complete process:
    - Starts the bot (workflow pauses)
    - When bot finishes, automatically resumes to process transcript
    - ProcessTranscriptStep handles: Q&A parsing, insights, summary, email, webhook

    **Request:**
    ```json
    {
      "room_url": "https://domain.daily.co/room-name",
      "token": "optional-meeting-token",
      "bot_config": {
        "bot_prompt": "You are a helpful AI assistant...",
        "name": "BotName",
        "video_mode": "static",
        "static_image": "robot01.png"
      },
      "process_insights": true
    }
    ```

    **Response:**
    ```json
    {
      "status": "started",
      "bot_id": "uuid",
      "room_url": "https://domain.daily.co/room-name"
    }
    ```

    The bot runs in the background. Use GET /v1/api/bot/{bot_id}/status to check progress.

    Use: POST /v1/api/bot/join
    """
    try:
        # Check credits before processing
        # Simple Explanation: We check if the user has sufficient credits before starting
        # the bot. This prevents starting expensive operations when credits are insufficient.
        # The check follows the error handling pattern from bot_call.py.
        credit_check_success, credit_error = check_credits_for_request(
            http_request, required_credits=0.15
        )
        if not credit_check_success:
            # Determine appropriate HTTP status code based on error type
            if credit_error.get("error") == "insufficient_credits":
                # Use custom JSONResponse for 402 to set "Insufficient Credits" status text
                return JSONResponse(
                    status_code=402,
                    content=credit_error,
                    headers={"X-Status-Reason": "Insufficient Credits"},
                )
            elif credit_error.get("error") == "user_not_found":
                status_code = 401  # Unauthorized for user not found
            elif credit_error.get("error") == "authentication_error":
                status_code = 401  # Unauthorized for auth errors
            else:
                status_code = 401  # Default to 401 for other errors
            # Pass the full error dict as detail (FastAPI supports dict for detail)
            raise HTTPException(
                status_code=status_code,
                detail=credit_error,
            )

        # Generate a unique bot_id for this bot session
        bot_id = str(uuid.uuid4())

        # Extract room name from URL (last part after the last slash)
        room_name = request.room_url.split("/")[-1]

        # Generate workflow_thread_id and save all configuration directly to workflow_threads
        # Simple Explanation:
        # - workflow_thread_id is OUR custom ID for tracking this workflow in our workflow_threads table
        # - We create it here BEFORE starting LangGraph, so we can save config to the database first
        # - This same ID will be used as LangGraph's thread_id (LangGraph uses it for checkpointing)
        # - LangGraph will also create a checkpoint_id when it pauses, which we'll save separately
        #
        # UUID4 Collision Safety:
        # - UUID4 has 2^122 possible values (5.3 x 10^36) - collision probability is astronomically low
        # - Database has PRIMARY KEY constraint on workflow_thread_id (enforces uniqueness)
        # - save_workflow_thread_data uses upsert, so collisions would update instead of fail
        # - We retry with a new UUID if save fails (extra safety)
        from flow.db import save_workflow_thread_data, get_workflow_thread_data

        # Retry logic for UUID collision (extremely unlikely but safe)
        max_retries = 3
        workflow_thread_id = None
        for attempt in range(max_retries):
            workflow_thread_id = str(uuid.uuid4())

            # Check if this ID already exists (extra safety check before saving)
            existing = get_workflow_thread_data(workflow_thread_id)
            if existing:
                logger.warning(
                    f"⚠️ UUID collision detected (attempt {attempt + 1}/{max_retries}): {workflow_thread_id} - generating new UUID"
                )
                continue  # Try again with new UUID

            # Extract API key ID from request state (set by Unkey middleware)
            unkey_key_id = None
            if hasattr(http_request.state, "unkey_key_id"):
                unkey_key_id = http_request.state.unkey_key_id
                logger.debug(
                    f"Extracted unkey_key_id from request state: {unkey_key_id}"
                )

            # Build workflow_thread_data with all configuration
            workflow_thread_data = {
                "workflow_thread_id": workflow_thread_id,
                "room_name": room_name,
                "room_url": request.room_url,
                "bot_id": bot_id,  # bot_id is defined above (line 310)
                # API key ID for user attribution
                "unkey_key_id": unkey_key_id,
                # Provider support (default: "daily")
                "provider": request.provider,
                # Email configuration (renamed from candidate_email)
                "email": request.email,
                "email_results_to": request.email,  # Use email as email_results_to
                # Processing configuration
                "analysis_prompt": request.analysis_prompt,
                "summary_format_prompt": request.summary_format_prompt,
                "webhook_callback_url": request.webhook_callback_url,
                # Bot configuration will be added in the workflow
                "meeting_status": "in_progress",
            }

            # Save to workflow_threads table
            if save_workflow_thread_data(workflow_thread_id, workflow_thread_data):
                logger.info(
                    f"✅ Saved configuration to workflow_threads: workflow_thread_id={workflow_thread_id}"
                )
                break  # Success - exit retry loop
            else:
                logger.warning(
                    f"⚠️ Failed to save workflow_thread_data (attempt {attempt + 1}/{max_retries}) - retrying with new UUID"
                )

        if not workflow_thread_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create workflow_thread_id after multiple attempts",
            )

        # Convert bot_config to dictionary format expected by bot_service
        # Default video_mode to "animated" if not provided
        video_mode = request.bot_config.video_mode or "animated"

        # Validate static_image is provided when video_mode="static"
        if video_mode == "static" and not request.bot_config.static_image:
            raise HTTPException(
                status_code=400,
                detail="static_image is required when video_mode='static'",
            )

        bot_config_dict = {
            "bot_prompt": request.bot_config.bot_prompt,
            "name": request.bot_config.name,
            "video_mode": video_mode,
        }

        # Only include static_image when video_mode="static"
        if video_mode == "static" and request.bot_config.static_image:
            bot_config_dict["static_image"] = request.bot_config.static_image

        # Include bot_greeting if provided
        if request.bot_config.bot_greeting:
            bot_config_dict["bot_greeting"] = request.bot_config.bot_greeting

        # Create bot session record in Supabase database
        bot_session_data = {
            "room_url": request.room_url,
            "room_name": room_name,
            "status": "running",
            "started_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": None,
            "process_insights": request.process_insights,
            "bot_config": bot_config_dict,
            "transcript_text": None,
            "qa_pairs": None,
            "insights": None,
            "error": None,
        }

        # Save to database
        if not save_bot_session(bot_id, bot_session_data):
            logger.error(f"❌ Failed to save bot session to database: bot_id={bot_id}")
            raise HTTPException(
                status_code=500, detail="Failed to save bot session to database"
            )

        # Add process_insights to bot_config so BotService knows to process insights
        bot_config_dict["process_insights"] = request.process_insights

        # Start the workflow instead of just starting the bot
        # Simple Explanation: The BotCallWorkflow orchestrates the complete process:
        # 1. Starts the bot (workflow pauses after this)
        # 2. When bot finishes, workflow resumes automatically
        # 3. ProcessTranscriptStep runs the full pipeline (Q&A, insights, email, webhook)
        from flow.workflows.bot_call import BotCallWorkflow

        workflow = BotCallWorkflow()

        # Prepare workflow context
        # Simple Explanation: We pass the workflow_thread_id so the workflow uses the existing
        # entry in workflow_threads instead of creating a new one.
        workflow_context = {
            "room_url": request.room_url,
            "token": request.token,
            "room_name": room_name,
            "bot_config": bot_config_dict,
            "bot_id": bot_id,
            "workflow_thread_id": workflow_thread_id,  # Pass existing workflow_thread_id
        }

        # Execute the workflow asynchronously
        # Simple Explanation: This starts the workflow which will:
        # 1. Start the bot (join_bot node)
        # 2. Pause and wait for bot to finish
        # 3. Resume automatically when bot finishes (via on_participant_left handler)
        # 4. Process transcript (process_transcript node)
        result = await workflow.execute_async(workflow_context)

        if not result.get("success"):
            # Workflow failed to start - update database
            error_msg = result.get("error", "Failed to start workflow")
            bot_session_data["status"] = "failed"
            bot_session_data["error"] = error_msg
            bot_session_data["completed_at"] = datetime.utcnow().isoformat() + "Z"
            save_bot_session(bot_id, bot_session_data)
            raise HTTPException(status_code=500, detail=error_msg)

        logger.info(
            f"✅ Bot workflow started: bot_id={bot_id}, room={room_name}, thread_id={result.get('thread_id')}"
        )

        return BotJoinResponse(
            status="started",
            bot_id=bot_id,
            room_url=request.room_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error starting bot: {str(e)}")


@v1_router.get("/api/bot/{bot_id}/status", response_model=BotStatusResponse)
async def get_bot_status_by_id_v1(bot_id: str) -> BotStatusResponse:
    """
    Get the status and results of a bot session (v1 API).

    **Simple Explanation:**
    This endpoint lets you check on a bot that was started via POST /v1/api/bot/join.
    It retrieves the bot session from the Supabase database and returns:
    - Current status (running, completed, or failed)
    - When it started and finished
    - The transcript, Q&A pairs, and insights (if processing is complete)

    **Response (while running):**
    ```json
    {
      "status": "running",
      "bot_id": "uuid",
      "room_url": "https://domain.daily.co/room-name",
      "started_at": "2025-01-15T10:00:00Z"
    }
    ```

    **Response (when finished):**
    ```json
    {
      "status": "completed",
      "bot_id": "uuid",
      "room_url": "https://domain.daily.co/room-name",
      "started_at": "2025-01-15T10:00:00Z",
      "completed_at": "2025-01-15T10:30:00Z",
      "transcript": "full transcript text...",
      "qa_pairs": [...],
      "insights": {...}
    }
    ```

    Use: GET /v1/api/bot/{bot_id}/status
    """
    # Get bot session from Supabase database
    session = get_bot_session(bot_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Bot session {bot_id} not found")

    # Check if bot is still running
    room_name = session["room_name"]
    is_running = bot_service.is_bot_running(room_name)

    # Update status if bot finished
    if session["status"] == "running" and not is_running:
        # Bot finished - update status in database
        session["status"] = "completed"
        session["completed_at"] = datetime.utcnow().isoformat() + "Z"

        # Get results from rooms table (bot_service saves them there)
        try:
            from flow.db import get_session_data

            session_data = get_session_data(room_name)
            if session_data:
                # Get transcript
                if session_data.get("transcript_text"):
                    session["transcript_text"] = session_data["transcript_text"]

                # Get Q&A pairs (if processed)
                if session_data.get("qa_pairs"):
                    session["qa_pairs"] = session_data["qa_pairs"]

                # Get insights (if processed)
                if session_data.get("insights"):
                    session["insights"] = session_data["insights"]
                elif session_data.get("candidate_summary"):
                    # If we have a summary but no insights, create a simple insights object
                    session["insights"] = {
                        "summary": session_data["candidate_summary"],
                    }

            # Update bot session in database with results
            save_bot_session(bot_id, session)

        except Exception as e:
            logger.error(f"Error retrieving bot results: {e}", exc_info=True)
            session["error"] = f"Error retrieving results: {str(e)}"
            save_bot_session(bot_id, session)

    return BotStatusResponse(
        status=session["status"],
        bot_id=session["bot_id"],
        room_url=session["room_url"],
        started_at=session.get("started_at"),
        completed_at=session.get("completed_at"),
        transcript=session.get("transcript_text"),
        qa_pairs=session.get("qa_pairs"),
        insights=session.get("insights"),
        error=session.get("error"),
    )


@v1_router.get("/bots/status")
async def get_bot_status_v1() -> dict[str, Any]:
    """
    Get status of all active bots (v1 API).

    Useful for monitoring and detecting long-running bots.

    Use: GET /v1/bots/status
    """
    from flow.steps.agent_call import bot_service

    active_bots = bot_service.list_active_bots()

    # Calculate totals
    total_bots = len(active_bots)
    total_runtime_hours = sum(
        bot.get("runtime_hours", 0) for bot in active_bots.values()
    )

    # Find long-running bots
    long_running = [
        {
            "room_name": name,
            "runtime_hours": bot.get("runtime_hours", 0),
            "warning": bot.get("warning"),
        }
        for name, bot in active_bots.items()
        if bot.get("runtime_hours", 0) > 1
    ]

    return {
        "total_active_bots": total_bots,
        "total_runtime_hours": round(total_runtime_hours, 2),
        "long_running_bots": long_running,
        "bots": active_bots,
    }


@v1_router.post("/bots/cleanup")
async def cleanup_bots_v1(max_hours: float = 2.0) -> dict[str, Any]:
    """
    Manually trigger cleanup of long-running bots (v1 API).

    Args:
        max_hours: Stop bots running longer than this (default: 2 hours)

    Use: POST /v1/bots/cleanup
    """
    from flow.steps.agent_call import bot_service

    stopped_count = await bot_service.cleanup_long_running_bots(max_hours)

    return {"status": "success", "bots_stopped": stopped_count, "max_hours": max_hours}


@v1_router.post("/bots/stop/{room_name}")
async def stop_bot_for_room_v1(room_name: str) -> dict[str, Any]:
    """
    Stop all bots for a specific room (v1 API).

    Useful for cleaning up duplicate bots or stopping bots manually.

    Use: POST /v1/bots/stop/{room_name}
    """
    from flow.steps.agent_call import bot_service

    success = await bot_service.stop_bot(room_name)

    return {
        "status": "success" if success else "not_found",
        "room_name": room_name,
        "message": (
            f"Bot stopped for room {room_name}"
            if success
            else f"No bot found for room {room_name}"
        ),
    }


# Include v1 router
app.include_router(v1_router)


# ============================================================================
# Unversioned Endpoints (Backward Compatibility - Deprecated)
# ============================================================================
# These keep old URLs working during transition period


@app.post("/api/bot/join", response_model=BotJoinResponse)
async def join_bot(request: BotJoinRequest, http_request: Request) -> BotJoinResponse:
    """
    Start a bot (unversioned - deprecated).

    ⚠️ DEPRECATED: Use POST /v1/api/bot/join instead.
    This endpoint will be removed on 2025-07-01.
    """
    # Simply call the v1 handler
    return await join_bot_v1(request, http_request)


@app.get("/api/bot/{bot_id}/status", response_model=BotStatusResponse)
async def get_bot_status_by_id(bot_id: str) -> BotStatusResponse:
    """
    Get bot status (unversioned - deprecated).

    ⚠️ DEPRECATED: Use GET /v1/api/bot/{bot_id}/status instead.
    """
    return await get_bot_status_by_id_v1(bot_id)


@app.get("/bots/status")
async def get_bot_status() -> dict[str, Any]:
    """
    Get all bots status (unversioned - deprecated).

    ⚠️ DEPRECATED: Use GET /v1/bots/status instead.
    """
    return await get_bot_status_v1()


@app.post("/bots/cleanup")
async def cleanup_bots(max_hours: float = 2.0) -> dict[str, Any]:
    """
    Cleanup bots (unversioned - deprecated).

    ⚠️ DEPRECATED: Use POST /v1/bots/cleanup instead.
    """
    return await cleanup_bots_v1(max_hours)


@app.post("/bots/stop/{room_name}")
async def stop_bot_for_room(room_name: str) -> dict[str, Any]:
    """
    Stop bot (unversioned - deprecated).

    ⚠️ DEPRECATED: Use POST /v1/bots/stop/{room_name} instead.
    """
    return await stop_bot_for_room_v1(room_name)


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Return empty favicon to prevent 401 errors."""
    return Response(status_code=204)  # No Content


@app.get("/meet/{room_name}", response_class=HTMLResponse)
async def serve_meeting_page(
    room_name: str,
    theme: str | None = Query("light", description="Theme: 'light' or 'dark'"),
    bgColor: str | None = Query(None, description="Background color (hex code)"),
    accentColor: str | None = Query(None, description="Accent color (hex code)"),
    textColor: str | None = Query(None, description="Text color (hex code)"),
    logo: str | None = Query(None, description="Logo image URL"),
    logoText: str | None = Query(None, description="Logo text"),
    interviewerContext: str | None = Query(
        None, description="Interviewer context for AI interviews"
    ),
) -> HTMLResponse:
    """
    Serve the hosted meeting page for a room.

    This endpoint serves a nice branded page where participants can join a video meeting.
    The room URL is automatically constructed from the room name using the DAILY_DOMAIN
    environment variable. You can customize the look and feel using query parameters.

    **Path Parameters:**
    - `room_name`: The Daily.co room name (e.g., "abc123")

    **Query Parameters:**
    - `theme`: 'light' or 'dark' theme
    - `bgColor`: Background color (hex code like #ffffff)
    - `accentColor`: Accent color (hex code like #3b82f6)
    - `textColor`: Text color (hex code)
    - `logo`: URL to logo image
    - `logoText`: Text to display as logo
    - `interviewerContext`: Context for AI interviewer (if applicable)

    **Example:**
    ```
    https://meet.pailkit.com/meet/abc123?theme=dark&accentColor=#60a5fa&logoText=MyCompany
    ```
    """
    try:
        # Get the path to the HTML template
        hosting_dir = Path(__file__).parent / "hosting"
        html_file = hosting_dir / "meeting.html"

        if not html_file.exists():
            logger.error(f"Meeting page template not found: {html_file}")
            raise HTTPException(
                status_code=500, detail="Meeting page template not found"
            )

        # Read the HTML template
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Inject DAILY_DOMAIN into the HTML template
        daily_domain = os.getenv("DAILY_DOMAIN", "https://your-domain.daily.co").rstrip(
            "/"
        )
        html_content = html_content.replace(
            "const DAILY_DOMAIN = null;", f'const DAILY_DOMAIN = "{daily_domain}";'
        )

        # The HTML template already handles query parameters via JavaScript
        # So we just need to serve it - the query params will be available in the URL
        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Error serving meeting page: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to serve meeting page: {str(e)}"
        )


# Webhook Handlers and Endpoints
# These functions handle webhooks from Daily.co that are routed by the Cloudflare Worker.
# The worker routes Daily.co webhooks here based on event type.


async def handle_meeting_ended_webhook(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle 'meeting.ended' webhook event from Daily.co.

    This function is called when a Daily.co meeting ends. It:
    1. Checks if there's a paused workflow waiting for the meeting to end
    2. Checks if bot was enabled (transcript in DB) or not (needs Daily.co transcript)
    3. Resumes the workflow to process the transcript

    This is more robust than processing immediately because it ensures:
    - Meeting is actually finished (not partial transcript)
    - Complete transcript is available (especially when bot is enabled)

    According to Daily.co docs: https://docs.daily.co/reference/rest-api/webhooks/events/meeting-ended
    """
    webhook_payload = payload.get("payload", payload)
    # Note: meeting.ended payload uses "room" (room_name) and "meeting_id" (not room_id)
    # See: https://docs.daily.co/reference/rest-api/webhooks/events/meeting-ended
    room_name = webhook_payload.get("room")  # This is the room name (not room_id)
    meeting_id = webhook_payload.get("meeting_id")  # This is the meeting UUID
    start_ts = webhook_payload.get("start_ts")
    end_ts = webhook_payload.get("end_ts")
    duration = (
        end_ts - start_ts if (end_ts and start_ts) else None
    )  # Calculate duration

    logger.info(f"🏁 Meeting ended webhook received for room: {room_name}")
    logger.info(f"   Meeting ID: {meeting_id}, Duration: {duration}s")

    try:
        from flow.db import get_session_data, save_session_data

        # Note: AIInterviewerWorkflow was removed in simplification
        # New bot system processes automatically when bot finishes
        try:
            from flow.workflows.ai_interviewer import AIInterviewerWorkflow
        except ImportError:
            AIInterviewerWorkflow = None

        # Check if there's a paused workflow for this room
        session_data = get_session_data(room_name) if room_name else None

        # CRITICAL: Check if transcript was already processed or is currently processing
        # This prevents multiple webhooks from all trying to process the same transcript
        transcript_already_processed = session_data and session_data.get(
            "transcript_processed", False
        )
        transcript_processing = session_data and session_data.get(
            "transcript_processing", False
        )

        if transcript_already_processed:
            logger.info(
                f"✅ Transcript already processed for room {room_name} - returning 200 OK immediately"
            )
            return {
                "status": "success",
                "room_name": room_name,
                "message": "Transcript already processed",
                "already_processed": True,
            }

        if transcript_processing:
            logger.info(
                f"⏳ Transcript is currently processing for room {room_name} - returning 200 OK immediately"
            )
            return {
                "status": "success",
                "room_name": room_name,
                "message": "Transcript is currently being processed",
                "already_processing": True,
            }

        workflow_paused = session_data and session_data.get("workflow_paused", False)
        thread_id = session_data.get("workflow_thread_id") if session_data else None
        waiting_for_meeting_ended = session_data and session_data.get(
            "waiting_for_meeting_ended", False
        )

        # Update meeting status in session data
        if session_data:
            session_data["meeting_status"] = "ended"
            session_data["meeting_end_time"] = end_ts
            session_data["meeting_start_time"] = start_ts
            save_session_data(room_name, session_data)
            logger.info(f"📝 Updated meeting status to 'ended' for room {room_name}")

        # Check what we're waiting for based on configuration flags
        waiting_for_transcript_webhook = session_data and session_data.get(
            "waiting_for_transcript_webhook", False
        )

        # Check if this is a OneTimeMeetingWorkflow (no checkpoints) or AIInterviewerWorkflow (with checkpoints)
        # OneTimeMeetingWorkflow rooms won't have workflow_paused or thread_id, but will have waiting_for_meeting_ended

        # Resume workflow if it was paused, OR if bot was enabled (waiting_for_meeting_ended)
        if (workflow_paused and thread_id) or waiting_for_meeting_ended:
            # Check if workflow is available (may not be if using new simplified bot system)
            if AIInterviewerWorkflow is None:
                logger.info(
                    "⚠️ AIInterviewerWorkflow not available - new simplified bot system processes automatically"
                )
                # For new simplified bot system, processing happens automatically in BotService
                # when the bot finishes. No need to resume workflow.
                return {
                    "status": "success",
                    "room_name": room_name,
                    "message": "Bot processes automatically - no workflow to resume",
                }

            # If we have a thread_id, try to resume from checkpoint
            if workflow_paused and thread_id:
                logger.info(f"🔄 Resuming paused workflow with thread_id: {thread_id}")
            elif waiting_for_meeting_ended:
                logger.info("🤖 Bot was enabled - meeting ended, processing transcript")
                if thread_id:
                    logger.info(f"   Using thread_id: {thread_id} to resume workflow")
                else:
                    logger.info(
                        "   No thread_id found - will process transcript directly"
                    )

            # Create workflow instance (must use same instance to access same checkpointer)
            if AIInterviewerWorkflow is None:
                logger.info(
                    "⚠️ AIInterviewerWorkflow not available - new simplified bot system processes automatically"
                )
                return {
                    "status": "success",
                    "room_name": room_name,
                    "message": "Bot processes automatically - no workflow to resume",
                }
            workflow = AIInterviewerWorkflow()

            # Config with thread_id to resume from checkpoint (if available)
            config = {"configurable": {"thread_id": thread_id}} if thread_id else None

            # Get the latest checkpoint state (only if we have a thread_id)
            if config:
                try:
                    # Get the latest checkpoint for this thread
                    # checkpointer.list() returns an iterator of (checkpoint_id, checkpoint_data) tuples
                    checkpoints = list(workflow.checkpointer.list(config))
                    if checkpoints:
                        # Get the latest checkpoint - checkpoints[-1] is a tuple (checkpoint_id, checkpoint_data)
                        # Access checkpoint_id as the first element of the tuple
                        latest_checkpoint_tuple = checkpoints[-1]
                        if isinstance(latest_checkpoint_tuple, tuple):
                            latest_checkpoint_id = latest_checkpoint_tuple[0]
                        else:
                            # Fallback: if it's a dict, use the old way
                            latest_checkpoint_id = (
                                latest_checkpoint_tuple.get("checkpoint_id")
                                if isinstance(latest_checkpoint_tuple, dict)
                                else str(latest_checkpoint_tuple)
                            )
                        checkpoint_tuple = await workflow.checkpointer.aget_tuple(
                            config, {"checkpoint_id": latest_checkpoint_id}
                        )
                        checkpoint, returned_checkpoint_id, parent_checkpoint_id = (
                            checkpoint_tuple
                        )

                        if checkpoint and checkpoint.get("channel_values"):
                            # Get current state from checkpoint
                            current_state = checkpoint["channel_values"]

                            if waiting_for_meeting_ended:
                                # Bot was enabled - transcript is in DB, resume workflow now
                                logger.info(
                                    "🤖 Bot was enabled - using transcript from database"
                                )
                                logger.info(
                                    "   ✅ Meeting ended - resuming workflow with DB transcript"
                                )
                                # Don't set transcript_id - process_transcript will use DB transcript
                            elif waiting_for_transcript_webhook:
                                # Frontend transcription enabled - need to wait for transcript.ready-to-download webhook
                                logger.info(
                                    "📥 Frontend transcription enabled - waiting for transcript.ready-to-download webhook"
                                )
                                logger.info(
                                    "   ⏸️  Not resuming workflow yet - will resume when transcript webhook arrives"
                                )
                                return {
                                    "status": "waiting_for_transcript",
                                    "room_name": room_name,
                                    "message": "Meeting ended - waiting for transcript.ready-to-download webhook",
                                }
                            else:
                                # Neither flag set - shouldn't happen, but handle gracefully
                                logger.warning(
                                    "⚠️ No waiting flags set - checking for transcript in DB as fallback"
                                )
                                transcript_in_db = session_data and session_data.get(
                                    "transcript_text"
                                )
                                if transcript_in_db:
                                    logger.info(
                                        "   ✅ Found transcript in DB - resuming workflow"
                                    )
                                    # Don't set transcript_id - process_transcript will use DB transcript
                                else:
                                    logger.warning(
                                        "   ⚠️ No transcript in DB - waiting for transcript webhook"
                                    )
                                    return {
                                        "status": "waiting_for_transcript",
                                        "room_name": room_name,
                                        "message": "Meeting ended - waiting for transcript.ready-to-download webhook",
                                    }

                            # Update state with meeting end info
                            current_state["room_id"] = (
                                meeting_id  # Use meeting_id as room_id
                            )
                            current_state["duration"] = duration
                            current_state["meeting_ended"] = True

                            # Mark as processing immediately to prevent duplicate webhooks
                            if session_data and room_name:
                                session_data["transcript_processing"] = True
                                save_session_data(room_name, session_data)

                            # Resume the workflow from where it paused in background
                            # LangGraph will continue from the interrupt point
                            async def resume_workflow():
                                await workflow.graph.ainvoke(
                                    current_state, config=config
                                )

                            background_tasks.add_task(resume_workflow)

                            # Return 200 OK immediately so webhook doesn't timeout
                            # Processing will happen in background
                            logger.info(
                                "🚀 Added workflow resume to background tasks - returning 200 OK immediately"
                            )
                            return {
                                "status": "success",
                                "room_name": room_name,
                                "message": "Workflow resumed in background",
                            }
                        else:
                            raise ValueError("Checkpoint state not found")
                    else:
                        raise ValueError("No checkpoints found for thread")
                except Exception as e:
                    # Fallback: if checkpoint retrieval fails, process transcript directly
                    logger.warning(
                        f"⚠️ Could not resume workflow from checkpoint: {e}, processing transcript directly"
                    )
                    # Process transcript directly (same logic as else block below)
                    from flow.steps.agent_call import (
                        ProcessTranscriptStep,
                    )

                    # Check what we're waiting for
                    waiting_for_meeting_ended = session_data and session_data.get(
                        "waiting_for_meeting_ended", False
                    )
                    if waiting_for_meeting_ended:
                        # Bot was enabled - transcript is in DB
                        logger.info(
                            "🤖 Bot was enabled - using transcript from database"
                        )
                        transcript_id = None  # Will be None if using DB transcript
                    else:
                        # Frontend transcription - use transcript_id from webhook
                        logger.info(
                            "📥 Frontend transcription - using transcript_id from webhook"
                        )
                        transcript_id = None  # Will be set from webhook if available

                    state = {
                        "transcript_id": transcript_id,  # May be None if using DB transcript
                        "room_id": meeting_id,  # Use meeting_id as room_id
                        "room_name": room_name,
                        "duration": duration,
                        "meeting_ended": True,
                        "workflow_thread_id": thread_id,  # Pass thread_id for per-workflow tracking
                    }

                    # Mark as processing immediately to prevent duplicate webhooks
                    if session_data and room_name:
                        session_data["transcript_processing"] = True
                        save_session_data(room_name, session_data)

                    # Add processing to background tasks - return 200 OK immediately
                    step = ProcessTranscriptStep()
                    background_tasks.add_task(step.execute, state)

                    # Return 200 OK immediately so webhook doesn't timeout
                    # Processing will happen in background
                    logger.info(
                        "🚀 Added transcript processing to background tasks - returning 200 OK immediately"
                    )
                    return {
                        "status": "success",
                        "room_name": room_name,
                        "message": "Transcript processing started in background",
                    }
            else:
                # No thread_id - process transcript directly (OneTimeMeetingWorkflow or direct processing)
                logger.info(
                    "   No thread_id available - processing transcript directly"
                )
                from flow.steps.agent_call.steps.process_transcript import (
                    ProcessTranscriptStep,
                )

                # Check what we're waiting for
                waiting_for_meeting_ended = session_data and session_data.get(
                    "waiting_for_meeting_ended", False
                )
                if waiting_for_meeting_ended:
                    # Bot was enabled - transcript is in DB
                    logger.info("🤖 Bot was enabled - using transcript from database")
                    transcript_id = None  # Will be None if using DB transcript
                else:
                    # Frontend transcription - use transcript_id from webhook
                    logger.info(
                        "📥 Frontend transcription - using transcript_id from webhook"
                    )
                    transcript_id = None  # Will be set from webhook if available

                # Get workflow_thread_id from session_data if available
                workflow_thread_id = (
                    session_data.get("workflow_thread_id") if session_data else None
                )

                state = {
                    "transcript_id": transcript_id,  # May be None if using DB transcript
                    "room_id": meeting_id,  # Use meeting_id as room_id
                    "room_name": room_name,
                    "duration": duration,
                    "meeting_ended": True,
                    "workflow_thread_id": workflow_thread_id,  # Pass thread_id for per-workflow tracking
                }

                # Mark as processing immediately to prevent duplicate webhooks
                if session_data and room_name:
                    session_data["transcript_processing"] = True
                    save_session_data(room_name, session_data)

                # Add processing to background tasks - return 200 OK immediately
                step = ProcessTranscriptStep()
                background_tasks.add_task(step.execute, state)

                # Return 200 OK immediately so webhook doesn't timeout
                # Processing will happen in background
                logger.info(
                    "🚀 Added transcript processing to background tasks - returning 200 OK immediately"
                )
                return {
                    "status": "success",
                    "room_name": room_name,
                    "message": "Transcript processing started in background",
                }
        else:
            # No paused workflow - just log the meeting end
            logger.info(
                f"📝 Meeting ended for room {room_name} (no paused workflow to resume)"
            )
            return {
                "status": "success",
                "room_name": room_name,
                "message": "Meeting ended - no workflow to resume",
            }

    except Exception as e:
        logger.error(f"❌ Meeting ended webhook error: {e}", exc_info=True)
        return {
            "status": "error",
            "room_name": room_name,
            "error": str(e),
        }


@app.post("/webhooks/meeting-ended")
async def webhook_meeting_ended(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle 'meeting.ended' webhook from Daily.co.

    **Important:** This is a webhook endpoint that returns 200 OK immediately
    and processes in the background. This prevents timeouts from Daily.co.
    Unlike regular API endpoints, webhooks don't validate input strictly -
    they're fire-and-forget notifications from Daily.co.

    This endpoint is called when a Daily.co meeting ends. It:
    1. Checks if transcript was already processed (prevents duplicates)
    2. Checks if there's a paused workflow waiting for the meeting to end
    3. Checks if bot was enabled (transcript in DB) or not (needs Daily.co transcript)
    4. Returns 200 OK immediately and processes transcript in background

    This is more robust than processing immediately because it ensures:
    - Meeting is actually finished (not partial transcript)
    - Complete transcript is available (especially when bot is enabled)
    - No timeouts from Daily.co webhook retries

    **Error Handling:**
    This endpoint ALWAYS returns 200 OK, even on errors, to prevent Daily.co
    from retrying the webhook. Errors are logged but don't cause 500 responses.

    See: https://docs.daily.co/reference/rest-api/webhooks/events/meeting-ended
    """
    try:
        result = await handle_meeting_ended_webhook(payload, background_tasks)
        return result
    except Exception as e:
        # **CRITICAL:** Always return 200 OK for webhooks, even on errors
        # This prevents Daily.co from retrying the webhook repeatedly
        # Daily.co will retry on 5xx errors, which can cause duplicate processing
        logger.error(f"❌ Error handling meeting.ended webhook: {e}", exc_info=True)

        # Extract room name from payload for logging
        webhook_payload = payload.get("payload", payload)
        room_name = webhook_payload.get("room", "unknown")

        # Return 200 OK with error details (but don't raise HTTPException)
        # This tells Daily.co the webhook was received, even if processing failed
        return {
            "status": "error",
            "room_name": room_name,
            "message": "Webhook received but processing failed",
            "error": str(e),
            "note": "This error was logged. Please check server logs for details.",
        }


# Server Startup

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
