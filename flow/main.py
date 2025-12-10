# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PailFlow FastAPI Application

Main entry point for the PailFlow API server with REST API and MCP integration.
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
    BackgroundTasks,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, Response  # noqa: E402
from mcp.server import FastMCP  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402
from shared.auth import UnkeyAuthMiddleware  # noqa: E402

from flow.workflows import (  # noqa: E402
    WorkflowNotFoundError,
    get_workflow,
    get_workflows,
)

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
    description="Workflow orchestration system with MCP integration",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(UnkeyAuthMiddleware)

mcp = FastMCP("PailFlow")


# Shared Business Logic


def list_workflows_logic() -> dict[str, Any]:
    """List all available workflows."""
    workflows_dict = get_workflows()
    workflows_list = [
        {
            "name": name,
            "description": getattr(workflow, "description", f"Workflow: {name}"),
        }
        for name, workflow in workflows_dict.items()
    ]

    return {
        "workflows": workflows_list,
        "count": len(workflows_list),
    }


def execute_workflow_logic(
    workflow_name: str,
    message: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute a workflow with context.

    Raises:
        WorkflowNotFoundError: If the workflow doesn't exist
        ValueError: If message is missing or empty
    """
    if not message or not message.strip():
        raise ValueError("Missing required field: message")

    logger.info(
        f"Executing workflow '{workflow_name}' with message: {message[:100]}..."
    )

    workflow = get_workflow(workflow_name)
    result = workflow.execute(
        message=message,
        user_id=user_id,
        channel_id=channel_id,
    )

    logger.info(f"Workflow '{workflow_name}' executed successfully")
    return result


def get_workflow_info_logic(workflow_name: str) -> dict[str, Any]:
    """Get detailed information about a workflow."""
    workflow = get_workflow(workflow_name)

    info = {
        "name": workflow_name,
        "description": getattr(workflow, "description", "No description available"),
        "parameters": getattr(workflow, "parameters", {}),
        "outputs": getattr(workflow, "outputs", {}),
    }

    if hasattr(workflow, "metadata"):
        info["metadata"] = workflow.metadata

    return info


def create_error_response(
    error: str,
    workflow_name: str | None = None,
    available_workflows: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a standardized error response structure.

    Used by both REST API endpoints and MCP tools for consistent error handling.
    """
    response: dict[str, Any] = {"error": error}
    if workflow_name:
        response["workflow_name"] = workflow_name
    if available_workflows:
        response["available_workflows"] = available_workflows
    return response


# REST API Endpoints


class WorkflowRequest(BaseModel):
    """Request model for workflow execution."""

    message: str = Field(
        ...,
        description="The message or input data for the workflow",
        min_length=1,
        max_length=10000,
    )
    user_id: str | None = Field(
        None, description="Optional user identifier for context"
    )
    channel_id: str | None = Field(
        None, description="Optional channel identifier for context"
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("Message cannot be empty or only whitespace")
        return v.strip()


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "pailflow"}


# ============================================================================
# Bot API Router
# ============================================================================
# Simple API for joining bots to existing Daily rooms, transcribing, and processing results

import uuid  # noqa: E402
from datetime import datetime  # noqa: E402

from flow.steps.agent_call.bot.bot_service import bot_service  # noqa: E402
from flow.db import save_bot_session, get_bot_session  # noqa: E402


# Pydantic models for bot API
class BotConfig(BaseModel):
    """Bot configuration for joining a room."""

    bot_prompt: str
    name: str = "PailBot"
    video_mode: str = "animated"  # "static" or "animated"
    static_image: str = "robot01.png"


class BotJoinRequest(BaseModel):
    """Request to start a bot in an existing room."""

    room_url: str  # Full Daily.co room URL
    token: str | None = None  # Optional meeting token
    bot_config: BotConfig
    process_insights: bool = True  # Whether to extract insights after bot finishes

    # Optional: Candidate/interview configuration
    candidate_name: str | None = None  # Candidate/participant name
    candidate_email: str | None = None  # Email to send results to
    interview_type: str | None = None  # Type of interview (e.g., "Technical Interview")
    position: str | None = None  # Job position being interviewed for
    interviewer_context: str | None = None  # Context about the interviewer/interview
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


@app.post("/api/bot/join", response_model=BotJoinResponse)
async def join_bot(request: BotJoinRequest, http_request: Request) -> BotJoinResponse:
    """
    Start a bot in an existing Daily room using the BotCallWorkflow.

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

    The bot runs in the background. Use GET /api/bot/{bot_id}/status to check progress.
    """
    try:
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
                # Candidate/interview configuration
                "candidate_name": request.candidate_name,
                "candidate_email": request.candidate_email,
                "email_results_to": request.candidate_email,  # Use candidate_email as email_results_to
                "interview_type": request.interview_type,
                "position": request.position,
                "interviewer_context": request.interviewer_context,
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
        bot_config_dict = {
            "bot_prompt": request.bot_config.bot_prompt,
            "name": request.bot_config.name,
            "video_mode": request.bot_config.video_mode,
            "static_image": request.bot_config.static_image,
        }

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


@app.get("/api/bot/{bot_id}/status", response_model=BotStatusResponse)
async def get_bot_status_by_id(bot_id: str) -> BotStatusResponse:
    """
    Get the status and results of a bot session.

    **Simple Explanation:**
    This endpoint lets you check on a bot that was started via POST /api/bot/join.
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


# ============================================================================
# Rooms API Router
# ============================================================================

from flow.rooms.providers.daily import DailyRooms  # noqa: E402


class RoomCreateRequest(BaseModel):
    """Request model for creating a room."""

    profile: str = "conversation"
    overrides: dict[str, Any] | None = None


def get_rooms_provider(provider_name: str, api_key: str) -> DailyRooms:
    """Create a provider instance with user-provided API key."""
    normalized_provider = provider_name.lower().strip()

    if normalized_provider == "daily":
        return DailyRooms(api_key=api_key)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider_name}. Supported: daily",
        )


@app.post("/api/rooms/create")
async def create_room(
    request: RoomCreateRequest,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """
    Create a new room for video, audio, or live collaboration.

    **Authentication:**
    Provide your provider API key via the `X-Provider-Auth` header:
    - Format: `Bearer <your-api-key>` or just `<your-api-key>`
    - For Daily.co: Get your API key from https://dashboard.daily.co/developers

    **Providers:**
    Specify provider via `X-Provider` header (default: "daily")
    - `daily` - Daily.co video rooms

    **Available profiles:**
    - `conversation` - Standard video chat
    - `audio_room` - Audio-only conversation
    - `broadcast` - One-to-many presentation
    - `podcast` - Audio recording session
    - `live_stream` - Stream to external platforms
    - `workshop` - Interactive collaborative session
    """
    try:
        provider_name = x_provider.lower().strip() if x_provider else "daily"
        api_key = x_provider_auth.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="X-Provider-Auth header is required. Provide your provider API key.",
            )

        provider = get_rooms_provider(provider_name, api_key)
        result: dict[str, Any] = await provider.create_room(
            profile=request.profile, overrides=request.overrides
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create room: {str(e)}"
        ) from e


@app.delete("/api/rooms/delete/{room_name}")
async def delete_room(
    room_name: str,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """Delete a room."""
    try:
        provider_name = x_provider.lower().strip() if x_provider else "daily"
        api_key = x_provider_auth.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="X-Provider-Auth header is required. Provide your provider API key.",
            )

        provider_instance = get_rooms_provider(provider_name, api_key)
        result: dict[str, Any] = await provider_instance.delete_room(room_name)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete room: {str(e)}"
        ) from e


@app.get("/api/rooms/get/{room_name}")
async def get_room(
    room_name: str,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """Get room details."""
    try:
        provider_name = x_provider.lower().strip() if x_provider else "daily"
        api_key = x_provider_auth.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="X-Provider-Auth header is required. Provide your provider API key.",
            )

        provider_instance = get_rooms_provider(provider_name, api_key)
        result: dict[str, Any] = await provider_instance.get_room(room_name)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get room: {str(e)}"
        ) from e


# ============================================================================
# Transcription API Router
# ============================================================================

from flow.transcribe.config_builder import build_config  # noqa: E402
from flow.transcribe.providers.base import TranscriptionProvider  # noqa: E402


class StartTranscriptionRequest(BaseModel):
    """Request model for starting a transcription."""

    profile: str = "meeting"
    audio_url: str | None = None
    overrides: dict[str, Any] | None = None


class StopTranscriptionRequest(BaseModel):
    """Request model for stopping a transcription."""

    transcription_id: str


def extract_provider_api_key(x_provider_auth: str) -> str:
    """Extract API key from X-Provider-Auth header."""
    api_key = x_provider_auth.strip()
    if api_key.startswith("Bearer "):
        api_key = api_key[7:].strip()

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="X-Provider-Auth header is required. Provide your provider API key.",
        )

    return api_key


def get_transcribe_provider(provider_name: str, api_key: str) -> TranscriptionProvider:
    """Create a transcription provider instance with user-provided API key."""
    _normalized_provider = provider_name.lower().strip()

    if _normalized_provider == "daily":
        from flow.transcribe.providers.daily import DailyTranscription

        return DailyTranscription(api_key=api_key)

    raise HTTPException(
        status_code=400,
        detail=f"Transcription provider not yet implemented: {provider_name}. "
        "Supported providers: daily. More providers will be added in future updates.",
    )


@app.post("/api/transcribe/start")
async def start_transcription(
    request: StartTranscriptionRequest,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """
    Start a real-time or streaming transcription.

    Begins transcribing audio in real-time from live streams, audio URLs, or direct input.
    Requires X-Provider-Auth header with provider API key and optional X-Provider header.

    Available profiles: meeting, general, medical, finance, podcast.
    """
    try:
        provider_name = x_provider.lower().strip() if x_provider else "daily"
        api_key = extract_provider_api_key(x_provider_auth)
        provider = get_transcribe_provider(provider_name, api_key)

        config = build_config(profile=request.profile, overrides=request.overrides)

        result: dict[str, Any] = await provider.start_transcription(
            audio_url=request.audio_url, config=config
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=500, detail=result.get("message", "Unknown error")
            )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start transcription: {str(e)}"
        ) from e


@app.post("/api/transcribe/stop")
async def stop_transcription(
    request: StopTranscriptionRequest,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """
    Stop an active transcription session.

    Stops a transcription started with /start and returns the final transcript.
    Requires X-Provider-Auth header with provider API key.
    """
    try:
        if not request.transcription_id:
            raise HTTPException(status_code=400, detail="transcription_id is required")

        provider_name = x_provider.lower().strip() if x_provider else "daily"
        api_key = extract_provider_api_key(x_provider_auth)
        provider = get_transcribe_provider(provider_name, api_key)

        result: dict[str, Any] = await provider.stop_transcription(
            request.transcription_id
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=500, detail=result.get("message", "Unknown error")
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop transcription: {str(e)}"
        ) from e


@app.get("/bots/status")
async def get_bot_status() -> dict[str, Any]:
    """
    Get status of all active bots.

    Useful for monitoring and detecting long-running bots.
    """
    from flow.steps.interview.bot_service import bot_service

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


@app.post("/bots/cleanup")
async def cleanup_bots(max_hours: float = 2.0) -> dict[str, Any]:
    """
    Manually trigger cleanup of long-running bots.

    Args:
        max_hours: Stop bots running longer than this (default: 2 hours)
    """
    from flow.steps.interview.bot_service import bot_service

    stopped_count = await bot_service.cleanup_long_running_bots(max_hours)

    return {"status": "success", "bots_stopped": stopped_count, "max_hours": max_hours}


@app.post("/bots/stop/{room_name}")
async def stop_bot_for_room(room_name: str) -> dict[str, Any]:
    """
    Stop all bots for a specific room.

    Useful for cleaning up duplicate bots or stopping bots manually.
    """
    from flow.steps.interview.bot_service import bot_service

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


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Return empty favicon to prevent 401 errors."""
    return Response(status_code=204)  # No Content


@app.get("/test-embed", response_class=HTMLResponse)
async def test_embed() -> HTMLResponse:
    """
    Serve a test page for the embeddable widget.

    This endpoint serves a simple test page where you can test the embeddable
    widget by entering a room name. Useful for development and testing.
    """
    try:
        test_file = Path(__file__).parent / "hosting" / "test-embed.html"
        if not test_file.exists():
            raise HTTPException(status_code=404, detail="Test page not found")
        with open(test_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        logger.error(f"Error serving test page: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to serve test page: {str(e)}"
        )


@app.get("/embed.js")
async def serve_embed_script() -> Response:
    """
    Serve the embeddable JavaScript widget for video meetings.

    This endpoint serves a JavaScript file that creates a video meeting widget
    that can be embedded in any website. The DAILY_DOMAIN is automatically
    injected into the script so users don't need to provide it.

    **Usage:**
    ```html
    <div id="meeting-container" style="width: 100%; height: 600px;"></div>
    <script src="https://your-domain.com/embed.js"></script>
    <script>
      PailFlow.init({
        container: '#meeting-container',
        roomName: 'my-room-123'
      });
    </script>
    ```

    **Note:** The Daily.co SDK is automatically loaded by the embed script, so you don't need to include it separately.

    **Configuration Options:**
    - `container` (required): CSS selector or DOM element for the widget
    - `roomName` (required): Daily.co room name
    - `token` (optional): Meeting token for authenticated rooms
    - `accentColor` (optional): Accent color hex code (default: '#1f2de6')
    - `logoText` (optional): Logo text (default: 'PailFlow')
    - `showHeader` (optional): Show header (default: true)
    - `showBrandLine` (optional): Show top brand line (default: true)
    - `autoRecord` (optional): Auto-start recording (default: false)
    - `autoTranscribe` (optional): Auto-start transcription (default: false)
    - `onLoaded`, `onJoined`, `onLeft`, `onError`, etc.: Event callbacks
    """
    try:
        # Get the path to the JavaScript file
        hosting_dir = Path(__file__).parent / "hosting"
        js_file = hosting_dir / "embed.js"

        if not js_file.exists():
            logger.error(f"Embed script not found: {js_file}")
            raise HTTPException(status_code=500, detail="Embed script not found")

        # Read the JavaScript file
        with open(js_file, "r", encoding="utf-8") as f:
            js_content = f.read()

        # Inject DAILY_DOMAIN into the JavaScript file
        daily_domain = os.getenv("DAILY_DOMAIN", "https://your-domain.daily.co").rstrip(
            "/"
        )
        js_content = js_content.replace(
            "const DAILY_DOMAIN = null; // Will be replaced by server",
            f'const DAILY_DOMAIN = "{daily_domain}";',
        )

        # Return as JavaScript with proper content type
        return Response(
            content=js_content,
            media_type="application/javascript",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            },
        )

    except Exception as e:
        logger.error(f"Error serving embed script: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to serve embed script: {str(e)}"
        )


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


@app.get("/workflows")
async def list_workflows() -> dict[str, Any]:
    """List all available workflows."""
    try:
        return list_workflows_logic()
    except Exception as e:
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error listing workflows: {str(e)}",
        )


@app.post("/workflow/{workflow_name}")
async def execute_workflow(
    workflow_name: str, request: WorkflowRequest
) -> dict[str, Any]:
    """Execute a specific workflow with context."""
    try:
        return execute_workflow_logic(
            workflow_name=workflow_name,
            message=request.message,
            user_id=request.user_id,
            channel_id=request.channel_id,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except WorkflowNotFoundError:
        available_workflows = list(get_workflows().keys())
        logger.warning(f"Workflow not found: {workflow_name}")
        error_msg = f"Workflow '{workflow_name}' not found. Available workflows: {', '.join(available_workflows)}"
        raise HTTPException(status_code=404, detail=error_msg)

    except Exception as e:
        logger.error(f"Error executing workflow '{workflow_name}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error executing workflow: {str(e)}",
        )


# ============================================================================
# Flow Endpoints - Hosted Workflow Service
# ============================================================================


class StartBotRequest(BaseModel):
    """Request model for starting a bot conversation."""

    participant_info: dict[str, Any] = Field(
        ...,
        description="Participant information (name, email, role, etc.) - generic field for any use case",
    )
    meeting_config: dict[str, Any] = Field(
        ...,
        description="Meeting configuration with prompts for bot behavior, analysis, and summary formatting",
    )
    webhook_callback_url: str | None = Field(
        None,
        description="Optional webhook URL to receive results when complete",
    )
    email_results_to: str | None = Field(
        None,
        description="Optional email address to receive results",
    )

    @field_validator("participant_info")
    @classmethod
    def validate_participant_info(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate participant_info has required fields."""
        if not isinstance(v, dict):
            raise ValueError("participant_info must be a dictionary")
        if not v.get("name"):
            raise ValueError("participant_info must include 'name' field")
        return v

    @field_validator("meeting_config")
    @classmethod
    def validate_meeting_config(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate meeting_config is a dictionary."""
        if not isinstance(v, dict):
            raise ValueError("meeting_config must be a dictionary")
        # Ensure bot is enabled
        bot_config = v.get("bot", {})
        if not bot_config.get("enabled", False):
            raise ValueError("meeting_config.bot.enabled must be true")
        if not bot_config.get("bot_prompt"):
            raise ValueError("meeting_config.bot.bot_prompt is required")
        return v


# Keep old name for backwards compatibility
AIInterviewerRequest = StartBotRequest


def get_provider_keys() -> dict[str, str]:
    """
    Get provider API keys from environment variables.

    This function retrieves the service's provider API keys from environment
    variables. Since this is a hosted service, the keys are managed by the
    service, not provided by users.

    Returns:
        Dictionary with provider keys (e.g., {"room_provider_key": "...", "room_provider": "daily"})
    """
    daily_api_key = os.getenv("DAILY_API_KEY")
    if not daily_api_key:
        raise HTTPException(
            status_code=500,
            detail="Service configuration error: DAILY_API_KEY not found",
        )

    return {
        "room_provider_key": daily_api_key,
        "room_provider": "daily",
    }


@app.post("/api/flows/start-bot")
async def start_bot_conversation(
    request: StartBotRequest,
) -> dict[str, Any]:
    """
    Start a bot conversation with customizable prompts.

    This endpoint creates a video room with an AI bot that can be configured for any purpose
    (interviews, consultations, training, etc.). You provide:
    - Participant information (name, email, etc.)
    - Bot prompt (defines what the bot says/does)
    - Analysis prompt (defines how to analyze the conversation)
    - Summary format prompt (defines how to format results)
    - Optional webhook URL and email for results

    The endpoint returns immediately with a room URL where the conversation will take place.
    Results (transcript, analysis, summary) will be sent to your webhook URL when complete.

    **Key Features:**
    - Fully prompt-driven: Control bot behavior, analysis, and output format via text prompts
    - Generic: Not limited to interviews - use for any conversation scenario
    - Flexible: Customize analysis and summary format for your use case

    **Authentication:**
    Provide your PailKit API key via the `Authorization` header:
    - Format: `Bearer <your-pailkit-api-key>`
    - Get your key from your PailKit dashboard

    **Request Body:**
    ```json
    {
      "participant_info": {
        "name": "John Doe",
        "email": "john@example.com",
        "role": "Software Engineer"
      },
      "meeting_config": {
        "bot": {
          "enabled": true,
          "bot_prompt": "You are a friendly AI assistant conducting a technical interview. Ask questions about Python, system design, and problem-solving. Wait for responses before asking the next question."
        },
        "analysis_prompt": "Analyze this conversation transcript. Provide scores, strengths, and areas for improvement. Use {transcript} as a placeholder for the transcript.",
        "summary_format_prompt": "Format as a professional scorecard with overall score, competency breakdown, and detailed Q&A sections."
      },
      "webhook_callback_url": "https://your-app.com/webhooks/conversation-complete",
      "email_results_to": "results@example.com"
    }
    ```

    **Prompt Placeholders:**
    - In `analysis_prompt`, use `{transcript}` or `{qa_text}` to inject the conversation transcript
    - If no placeholder is used, the transcript will be appended automatically

    **Response:**
    Returns immediately with room URL and session info. Results sent via webhook when complete.

    **Example - Technical Interview:**
    ```bash
    curl -X POST https://api.pailkit.com/api/flows/start-bot \\
      -H "Authorization: Bearer <your-pailkit-key>" \\
      -H "Content-Type: application/json" \\
      -d '{
        "participant_info": {
          "name": "John Doe",
          "email": "john@example.com"
        },
        "meeting_config": {
          "bot": {
            "enabled": true,
            "bot_prompt": "You are conducting a technical interview. Ask questions about Python, system design, and problem-solving."
          },
          "analysis_prompt": "Analyze this interview transcript. Provide scores, strengths, and areas for improvement. Transcript: {transcript}",
          "summary_format_prompt": "Format as a scorecard with overall score, competency breakdown, and detailed Q&A."
        },
        "webhook_callback_url": "https://your-app.com/webhooks/interview-complete"
      }'
    ```

    **Example - Customer Support:**
    ```bash
    curl -X POST https://api.pailkit.com/api/flows/start-bot \\
      -H "Authorization: Bearer <your-pailkit-key>" \\
      -H "Content-Type: application/json" \\
      -d '{
        "participant_info": {
          "name": "Jane Smith",
          "email": "jane@example.com"
        },
        "meeting_config": {
          "bot": {
            "enabled": true,
            "bot_prompt": "You are a customer support agent. Help the customer with their issue. Be friendly and solution-oriented."
          },
          "analysis_prompt": "Analyze this support conversation. Identify the issue, resolution, and customer satisfaction. Transcript: {transcript}",
          "summary_format_prompt": "Format as a support ticket summary with issue description, resolution steps, and customer feedback."
        },
        "webhook_callback_url": "https://your-app.com/webhooks/support-complete"
      }'
    ```
    """
    try:
        # Get provider keys from environment variables (hosted service)
        provider_keys = get_provider_keys()

        # Prepare workflow context
        # Include webhook and email in meeting_config so they're saved to session data
        meeting_config = request.meeting_config.copy()
        if request.webhook_callback_url:
            meeting_config["webhook_callback_url"] = request.webhook_callback_url
        if request.email_results_to:
            meeting_config["email_results_to"] = request.email_results_to

        context = {
            "participant_info": request.participant_info,
            "meeting_config": meeting_config,
            "provider_keys": provider_keys,
        }

        # Use AI Interviewer workflow (it's generic enough for any bot conversation)
        workflow = get_workflow("ai_interviewer")

        # Execute the workflow asynchronously
        # We use execute_async() directly instead of execute() because:
        # 1. execute() creates a new event loop in a thread and closes it when done
        # 2. This kills the bot task which runs in that loop
        # 3. execute_async() runs in the current event loop, so the bot task keeps running
        result = await workflow.execute_async(context)

        # Check for errors
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error occurred")
            logger.error(f"❌ Workflow execution failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        # Extract results from workflow response
        # execute_async() returns the result directly (not wrapped in "results")
        processing_status = result.get("processing_status", "unknown")

        # Get hosted_url and room_url from workflow result (from one_time_meeting subgraph)
        # execute_async() returns these directly in the result dict
        hosted_url = result.get("hosted_url")
        room_url = result.get("room_url")
        room_name = result.get("room_name")

        # Get session_id - might be in result or in _state
        session_id = result.get("session_id") or result.get("_state", {}).get(
            "session_id"
        )

        # Build response with room information
        # Results will be sent via webhook when complete
        response = {
            "success": True,
            "message": "Bot conversation started successfully",
            "session_id": session_id,
            "room_url": room_url,
            "room_name": room_name,
            "hosted_url": hosted_url,  # The hosted meeting.html link
            "processing_status": processing_status,
            "note": (
                "Interview results will be sent to your webhook URL when complete. "
                "Use the hosted_url to join the interview."
            ),
        }

        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except WorkflowNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error starting bot conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Keep old endpoint for backwards compatibility
@app.post("/api/flows/ai-interviewer")
async def execute_ai_interviewer_workflow(
    request: AIInterviewerRequest,
) -> dict[str, Any]:
    """
    Execute the AI Interviewer workflow (deprecated - use /api/flows/start-bot instead).

    This endpoint is kept for backwards compatibility. New integrations should use /api/flows/start-bot.
    """
    # Delegate to the new endpoint
    return await start_bot_conversation(request)


# Webhook Handlers and Endpoints
# These functions handle webhooks from Daily.co that are routed by the Cloudflare Worker.
# The worker routes Daily.co webhooks here based on event type.


async def handle_recording_ready_to_download(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Handle 'recording.ready-to-download' webhook event.

    This function is called when a Daily.co recording is ready to download.
    According to Daily.co docs: https://docs.daily.co/reference/rest-api/webhooks/events/recording-ready-to-download

    You can add logic here to:
    - Download the recording from the provided URL
    - Process the video
    - Store metadata
    - Send notifications
    """
    # Daily.co webhook format has nested payload structure
    webhook_payload = payload.get("payload", payload)
    room_name = webhook_payload.get("room_name")
    recording_id = webhook_payload.get("recording_id")

    logger.info(f"Recording ready to download for room: {room_name}")
    logger.info(f"Recording ID: {recording_id}")

    # Extract additional info
    s3_key = webhook_payload.get("s3_key")
    duration = webhook_payload.get("duration")

    logger.info(f"S3 Key: {s3_key}")
    logger.info(f"Duration: {duration} seconds")

    # Add your custom logic here
    # Example: Download the recording, process it, store it, etc.
    # You can use the recording_id to fetch the download URL from Daily.co API if needed

    return {
        "status": "processed",
        "event": "recording.ready-to-download",
        "recording_id": recording_id,
        "room_name": room_name,
    }


async def handle_transcript_ready_to_download(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle 'transcript.ready-to-download' webhook event.

    This function is called when a Daily.co transcript is ready to download.
    It extracts the webhook data and triggers the ProcessTranscriptStep,
    which will fetch the download link via the Daily.co API.

    According to Daily.co docs: https://docs.daily.co/reference/rest-api/webhooks/events/transcript-ready-to-download
    """
    webhook_payload = payload.get("payload", payload)
    transcript_id = webhook_payload.get("id")
    room_id = webhook_payload.get("room_id")
    room_name = webhook_payload.get("room_name")
    duration = webhook_payload.get("duration")

    logger.info(f"📨 Transcript webhook received: {transcript_id}")

    try:
        from flow.db import get_session_data

        # Note: AIInterviewerWorkflow was removed in simplification
        # New bot system processes automatically when bot finishes
        try:
            from flow.workflows.ai_interviewer import AIInterviewerWorkflow
        except ImportError:
            AIInterviewerWorkflow = None

        # Check if there's a paused workflow for this room
        session_data = get_session_data(room_name) if room_name else None
        workflow_paused = session_data and session_data.get("workflow_paused", False)
        thread_id = session_data.get("workflow_thread_id") if session_data else None

        # Check if we're waiting for this webhook based on configuration
        waiting_for_transcript_webhook = session_data and session_data.get(
            "waiting_for_transcript_webhook", False
        )

        if workflow_paused and thread_id:
            # Only resume if we're actually waiting for this webhook
            # (or if no explicit waiting flag is set, for backward compatibility)
            if not waiting_for_transcript_webhook and session_data:
                # Check if we should be waiting for meeting.ended instead
                waiting_for_meeting_ended = session_data.get(
                    "waiting_for_meeting_ended", False
                )
                if waiting_for_meeting_ended:
                    logger.info(
                        "⏸️  Waiting for meeting.ended webhook, not transcript webhook"
                    )
                    return {
                        "status": "waiting_for_meeting",
                        "transcript_id": transcript_id,
                        "room_name": room_name,
                        "message": "Workflow is waiting for meeting.ended webhook, not transcript webhook",
                    }
            # Resume the paused workflow using thread_id
            logger.info(f"🔄 Resuming paused workflow with thread_id: {thread_id}")

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

            # Config with thread_id to resume from checkpoint
            config = {"configurable": {"thread_id": thread_id}}

            # Get the latest checkpoint state
            # LangGraph stores state in checkpoints, we need to get it and update it
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
                        # Update state with transcript_id from webhook
                        current_state["transcript_id"] = transcript_id
                        current_state["room_id"] = room_id
                        current_state["duration"] = duration

                        # Resume the workflow from where it paused
                        # LangGraph will continue from the interrupt point
                        result = await workflow.graph.ainvoke(
                            current_state, config=config
                        )
                    else:
                        raise ValueError("Checkpoint state not found")
                else:
                    raise ValueError("No checkpoints found for thread")
            except Exception as e:
                # Fallback: if checkpoint retrieval fails, process transcript directly
                logger.warning(
                    f"⚠️ Could not resume workflow from checkpoint: {e}, processing transcript directly"
                )
                from flow.steps.agent_call.steps.process_transcript import (
                    ProcessTranscriptStep,
                )

                # Get workflow_thread_id from session_data if available
                workflow_thread_id = (
                    session_data.get("workflow_thread_id") if session_data else None
                )

                state = {
                    "transcript_id": transcript_id,
                    "room_id": room_id,
                    "room_name": room_name,
                    "duration": duration,
                    "workflow_thread_id": workflow_thread_id,  # Pass thread_id for per-workflow tracking
                }
                step = ProcessTranscriptStep()
                result = await step.execute(state)

            # Check for errors
            if result.get("error"):
                return {
                    "status": "error",
                    "transcript_id": transcript_id,
                    "error": result.get("error"),
                }

            # Return success response
            candidate_name = result.get("candidate_info", {}).get("name", "Unknown")
            return {
                "status": "success",
                "transcript_id": transcript_id,
                "candidate_name": candidate_name,
                "webhook_sent": result.get("webhook_sent", False),
                "email_sent": result.get("email_sent", False),
                "workflow_resumed": True,
            }
        else:
            # No paused workflow - process transcript directly (legacy behavior)
            logger.info("📝 Processing transcript directly (no paused workflow)")
            from flow.steps.agent_call.steps.process_transcript import (
                ProcessTranscriptStep,
            )

            # Get workflow_thread_id from session_data if available
            from flow.db import get_session_data

            session_data = get_session_data(room_name) if room_name else None
            workflow_thread_id = (
                session_data.get("workflow_thread_id") if session_data else None
            )

            # Create state from webhook payload
            state = {
                "transcript_id": transcript_id,
                "room_id": room_id,
                "room_name": room_name,
                "duration": duration,
                "workflow_thread_id": workflow_thread_id,  # Pass thread_id for per-workflow tracking
            }

            # Execute the processing step
            step = ProcessTranscriptStep()
            result = await step.execute(state)

            # Check for errors
            if result.get("error"):
                return {
                    "status": "error",
                    "transcript_id": transcript_id,
                    "error": result.get("error"),
                }

            # Return success response
            return {
                "status": "success",
                "transcript_id": transcript_id,
                "candidate_name": result.get("candidate_info", {}).get("name"),
                "webhook_sent": result.get("webhook_sent", False),
                "email_sent": result.get("email_sent", False),
            }

    except Exception as e:
        logger.error(f"❌ Transcript webhook error: {e}", exc_info=True)
        return {
            "status": "error",
            "transcript_id": transcript_id,
            "error": str(e),
        }


@app.post("/webhooks/recording-ready-to-download")
async def webhook_recording_ready_to_download(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle 'recording.ready-to-download' webhook from Daily.co.

    This endpoint receives webhooks when a Daily.co recording is ready to download.
    The Cloudflare Worker routes 'recording.ready-to-download' events here.

    **Error Handling:**
    This endpoint ALWAYS returns 200 OK, even on errors, to prevent Daily.co
    from retrying the webhook. Errors are logged but don't cause 500 responses.

    See: https://docs.daily.co/reference/rest-api/webhooks/events/recording-ready-to-download
    """
    try:
        result = await handle_recording_ready_to_download(payload)
        return result
    except Exception as e:
        # **CRITICAL:** Always return 200 OK for webhooks, even on errors
        # This prevents Daily.co from retrying the webhook repeatedly
        logger.error(
            f"❌ Error handling recording.ready-to-download webhook: {e}", exc_info=True
        )
        webhook_payload = payload.get("payload", payload)
        room_name = webhook_payload.get("room_name", "unknown")
        return {
            "status": "error",
            "room_name": room_name,
            "message": "Webhook received but processing failed",
            "error": str(e),
            "note": "This error was logged. Please check server logs for details.",
        }


@app.post("/webhooks/transcript-ready-to-download")
async def webhook_transcript_ready_to_download(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle 'transcript.ready-to-download' webhook from Daily.co.

    This endpoint receives webhooks when a Daily.co transcript is ready to download.
    The Cloudflare Worker routes 'transcript.ready-to-download' events here.

    **Error Handling:**
    This endpoint ALWAYS returns 200 OK, even on errors, to prevent Daily.co
    from retrying the webhook. Errors are logged but don't cause 500 responses.

    See: https://docs.daily.co/reference/rest-api/webhooks/events/transcript-ready-to-download
    """
    try:
        result = await handle_transcript_ready_to_download(payload)
        return result
    except Exception as e:
        # **CRITICAL:** Always return 200 OK for webhooks, even on errors
        # This prevents Daily.co from retrying the webhook repeatedly
        logger.error(
            f"❌ Error handling transcript.ready-to-download webhook: {e}",
            exc_info=True,
        )
        webhook_payload = payload.get("payload", payload)
        room_name = webhook_payload.get("room_name", "unknown")
        return {
            "status": "error",
            "room_name": room_name,
            "message": "Webhook received but processing failed",
            "error": str(e),
            "note": "This error was logged. Please check server logs for details.",
        }


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
                    from flow.steps.interview.process_transcript import (
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


# MCP Tools


@mcp.tool()
def list_workflows_mcp() -> dict[str, Any]:
    """List all available workflows."""
    try:
        return list_workflows_logic()
    except Exception as e:
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        return create_error_response(f"Error listing workflows: {str(e)}")


@mcp.tool()
def execute_workflow_mcp(
    workflow_name: str,
    message: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Execute a specific workflow with context."""
    try:
        result = execute_workflow_logic(
            workflow_name=workflow_name,
            message=message,
            user_id=user_id,
            channel_id=channel_id,
        )

        return {
            "success": True,
            "result": result,
            "workflow_name": workflow_name,
        }

    except ValueError as e:
        logger.warning(f"Invalid request: {e}")
        return create_error_response(str(e), workflow_name=workflow_name)

    except WorkflowNotFoundError:
        available_workflows = list(get_workflows().keys())
        logger.warning(f"Workflow not found: {workflow_name}")
        error_msg = f"Workflow '{workflow_name}' not found"
        return create_error_response(
            error_msg,
            workflow_name=workflow_name,
            available_workflows=available_workflows,
        )

    except NotImplementedError:
        logger.warning(f"Workflow not yet implemented: {workflow_name}")
        return create_error_response(
            f"Workflow '{workflow_name}' is not yet implemented",
            workflow_name=workflow_name,
        )

    except Exception as e:
        logger.error(f"Error executing workflow '{workflow_name}': {e}", exc_info=True)
        return create_error_response(str(e), workflow_name=workflow_name)


@mcp.tool()
def get_workflow_info_mcp(workflow_name: str) -> dict[str, Any]:
    """Get detailed information about a workflow."""
    try:
        return get_workflow_info_logic(workflow_name)
    except WorkflowNotFoundError:
        logger.warning(f"Workflow not found: {workflow_name}")
        return create_error_response(
            f"Workflow '{workflow_name}' not found", workflow_name=workflow_name
        )
    except NotImplementedError:
        logger.warning(f"Workflow not yet implemented: {workflow_name}")
        return create_error_response(
            f"Workflow '{workflow_name}' is not yet implemented",
            workflow_name=workflow_name,
        )
    except Exception as e:
        logger.error(
            f"Error getting workflow info for '{workflow_name}': {e}", exc_info=True
        )
        return create_error_response(str(e), workflow_name=workflow_name)


@mcp.tool()
def order_food_mcp(
    query: str,
    customer: dict[str, Any],
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    dropoff_instructions: str | None = None,
    quantity: int = 1,
) -> dict[str, Any]:
    """
    Execute the order_food workflow via MCP with structured parameters.

    This tool orchestrates the complete food ordering process through the MealMe API:
    1. Geocodes address (if provided)
    2. Searches for products near the location
    3. Creates a shopping cart
    4. Adds the selected product to the cart
    5. Creates an order with customer details
    6. Retrieves a checkout link for payment

    Args:
        query: Product search term (e.g., "coffee", "Cold Brew")
        customer: Customer information dict with name, email, phone_number, and address
        address: Delivery address (optional if latitude/longitude provided)
        latitude: Latitude coordinate (optional if address provided)
        longitude: Longitude coordinate (optional if address provided)
        dropoff_instructions: Optional delivery instructions
        quantity: Quantity of product to order (default: 1)

    Returns:
        Dictionary with status, order_id, product name, and checkout_url
    """
    from flow.workflows.order_food import run as order_food_run

    try:
        params = {
            "query": query,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "customer": customer,
            "dropoff_instructions": dropoff_instructions,
            "quantity": quantity,
        }

        # Call the workflow's run function
        result = order_food_run(params)

        # Return the result directly (it already has the correct structure)
        return result

    except Exception as e:
        logger.error(f"Error executing order_food workflow via MCP: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Error executing order_food workflow: {str(e)}",
        }


# Mount FastMCP into FastAPI
app.mount("/mcp", mcp.streamable_http_app())


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
