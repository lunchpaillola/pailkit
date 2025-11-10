# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PailFlow FastAPI Application

Main entry point for the PailFlow API server with REST API and MCP integration.
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator
from shared.auth import UnkeyAuthMiddleware

from flow.workflows import WorkflowNotFoundError, get_workflow, get_workflows

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
