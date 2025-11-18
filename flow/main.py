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
