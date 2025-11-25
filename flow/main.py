# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PailFlow FastAPI Application

Main entry point for the PailFlow API server with REST API and MCP integration.
"""

import json
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
from fastapi import FastAPI, HTTPException, Query  # noqa: E402
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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

    **Simple Explanation:**
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


class AIInterviewerRequest(BaseModel):
    """Request model for AI Interviewer workflow execution."""

    candidate_info: dict[str, Any] = Field(
        ...,
        description="Candidate information (name, email, role, etc.)",
    )
    interview_config: dict[str, Any] = Field(
        ...,
        description="Interview configuration (type, duration, difficulty, etc.)",
    )
    webhook_callback_url: str | None = Field(
        None,
        description="Optional webhook URL to receive interview results when complete",
    )
    email_results_to: str | None = Field(
        None,
        description="Optional email address to receive interview results",
    )

    @field_validator("candidate_info")
    @classmethod
    def validate_candidate_info(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate candidate_info has required fields."""
        if not isinstance(v, dict):
            raise ValueError("candidate_info must be a dictionary")
        if not v.get("name"):
            raise ValueError("candidate_info must include 'name' field")
        return v

    @field_validator("interview_config")
    @classmethod
    def validate_interview_config(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate interview_config is a dictionary."""
        if not isinstance(v, dict):
            raise ValueError("interview_config must be a dictionary")
        return v


def get_provider_keys() -> dict[str, str]:
    """
    Get provider API keys from environment variables.

    **Simple Explanation:**
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


@app.post("/api/flows/ai-interviewer")
async def execute_ai_interviewer_workflow(
    request: AIInterviewerRequest,
) -> dict[str, Any]:
    """
    Execute the AI Interviewer workflow.

    **Simple Explanation:**
    This endpoint starts an AI-powered interview. You provide:
    - Candidate information (name, email, etc.)
    - Interview configuration (type, duration, etc.)
    - Optional webhook URL and email for results

    The endpoint returns immediately with a room URL where the interview will take place.
    Results (transcript, analysis, assessment) will be sent to your webhook URL when complete.

    **Authentication:**
    Provide your PailKit API key via the `Authorization` header:
    - Format: `Bearer <your-pailkit-api-key>`
    - Get your key from your PailKit dashboard

    **Request Body:**
    ```json
    {
      "candidate_info": {
        "name": "John Doe",
        "email": "john@example.com",
        "role": "Software Engineer"
      },
      "interview_config": {
        "type": "technical",
        "duration": 30,
        "difficulty": "medium"
      },
      "webhook_callback_url": "https://your-app.com/webhooks/interview-complete",
      "email_results_to": "hr@example.com"
    }
    ```

    **Response:**
    Returns immediately with room URL and session info. Results sent via webhook when complete.

    **Example:**
    ```bash
    curl -X POST https://api.pailkit.com/api/flows/ai-interviewer \\
      -H "Authorization: Bearer <your-pailkit-key>" \\
      -H "Content-Type: application/json" \\
      -d '{
        "candidate_info": {
          "name": "John Doe",
          "email": "john@example.com"
        },
        "interview_config": {
          "type": "technical",
          "duration": 30
        },
        "webhook_callback_url": "https://your-app.com/webhooks/interview-complete"
      }'
    ```
    """
    try:
        # Get provider keys from environment variables (hosted service)
        provider_keys = get_provider_keys()

        # Prepare workflow context
        # Include webhook and email in interview_config so they're saved to session data
        interview_config = request.interview_config.copy()
        if request.webhook_callback_url:
            interview_config["webhook_callback_url"] = request.webhook_callback_url
        if request.email_results_to:
            interview_config["email_results_to"] = request.email_results_to

        context = {
            "candidate_info": request.candidate_info,
            "interview_config": interview_config,
            "provider_keys": provider_keys,
        }

        # Get the AI Interviewer workflow
        workflow = get_workflow("ai_interviewer")

        # Execute the workflow
        # Note: The workflow.execute() method handles async execution internally
        result = workflow.execute(
            message=json.dumps(context),
            user_id=None,
            channel_id=None,
        )

        # Check for errors
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error occurred")
            logger.error(f"❌ Workflow execution failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        # Extract results from workflow response
        workflow_results = result.get("results", {})
        processing_status = result.get("processing_status", "unknown")

        # Get state from _state if available (when workflow is paused)
        state = result.get("_state", {})

        # Get hosted_url from workflow result (from one_time_meeting subgraph)
        # Check multiple places: direct result, _state, or workflow_results
        hosted_url = (
            state.get("hosted_url")
            or result.get("hosted_url")
            or workflow_results.get("hosted_url")
        )
        room_url = (
            state.get("room_url")
            or result.get("room_url")
            or workflow_results.get("room_url")
        )

        # Build response with room information
        # Results will be sent via webhook when complete
        response = {
            "success": True,
            "message": "Interview workflow started successfully",
            "session_id": workflow_results.get("session_id")
            or result.get("session_id"),
            "room_url": room_url,
            "hosted_url": hosted_url,  # The hosted meeting.html link
            "candidate_info": workflow_results.get("candidate_info")
            or result.get("candidate_info"),
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
        logger.error("AI Interviewer workflow not found")
        raise HTTPException(
            status_code=500, detail="AI Interviewer workflow is not available"
        )
    except Exception as e:
        logger.error(f"Error executing AI Interviewer workflow: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error executing interview workflow: {str(e)}",
        )


# Webhook Handlers and Endpoints
# **Simple Explanation:**
# These functions handle webhooks from Daily.co that are routed by the Cloudflare Worker.
# The worker routes Daily.co webhooks here based on event type.


async def handle_recording_ready_to_download(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Handle 'recording.ready-to-download' webhook event.

    **Simple Explanation:**
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

    **Simple Explanation:**
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
        from flow.workflows.ai_interviewer import AIInterviewerWorkflow

        # Check if there's a paused workflow for this room
        session_data = get_session_data(room_name) if room_name else None
        workflow_paused = session_data and session_data.get("workflow_paused", False)
        thread_id = session_data.get("workflow_thread_id") if session_data else None

        if workflow_paused and thread_id:
            # Resume the paused workflow using thread_id
            logger.info(f"🔄 Resuming paused workflow with thread_id: {thread_id}")

            # Create workflow instance (must use same instance to access same checkpointer)
            workflow = AIInterviewerWorkflow()

            # Config with thread_id to resume from checkpoint
            config = {"configurable": {"thread_id": thread_id}}

            # Get the latest checkpoint state
            # LangGraph stores state in checkpoints, we need to get it and update it
            try:
                # Get the latest checkpoint for this thread
                checkpoints = list(workflow.checkpointer.list(config))
                if checkpoints:
                    # Get the latest checkpoint
                    latest_checkpoint_id = checkpoints[-1]["checkpoint_id"]
                    checkpoint = workflow.checkpointer.get(
                        config, {"checkpoint_id": latest_checkpoint_id}
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
                from flow.steps.interview.process_transcript import (
                    ProcessTranscriptStep,
                )

                state = {
                    "transcript_id": transcript_id,
                    "room_id": room_id,
                    "room_name": room_name,
                    "duration": duration,
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
            from flow.steps.interview.process_transcript import ProcessTranscriptStep

            # Create state from webhook payload
            state = {
                "transcript_id": transcript_id,
                "room_id": room_id,
                "room_name": room_name,
                "duration": duration,
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

    **Simple Explanation:**
    This endpoint receives webhooks when a Daily.co recording is ready to download.
    The Cloudflare Worker routes 'recording.ready-to-download' events here.

    See: https://docs.daily.co/reference/rest-api/webhooks/events/recording-ready-to-download
    """
    try:
        result = await handle_recording_ready_to_download(payload)
        return result
    except Exception as e:
        logger.error(
            f"Error handling recording.ready-to-download webhook: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/transcript-ready-to-download")
async def webhook_transcript_ready_to_download(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Handle 'transcript.ready-to-download' webhook from Daily.co.

    **Simple Explanation:**
    This endpoint receives webhooks when a Daily.co transcript is ready to download.
    The Cloudflare Worker routes 'transcript.ready-to-download' events here.

    See: https://docs.daily.co/reference/rest-api/webhooks/events/transcript-ready-to-download
    """
    try:
        result = await handle_transcript_ready_to_download(payload)
        return result
    except Exception as e:
        logger.error(
            f"Error handling transcript.ready-to-download webhook: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


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
