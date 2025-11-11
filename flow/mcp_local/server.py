# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PailFlow MCP Server

This module provides a FastMCP server that exposes PailFlow workflows as MCP tools.
It allows AI agents to discover, inspect, and execute workflows through the
Model Context Protocol (MCP).
"""

import argparse
import logging
from typing import Any

import uvicorn
from mcp.server import FastMCP

from flow.workflows import (
    WorkflowNotFoundError,
    get_workflow,
    get_workflows,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Create FastMCP server instance
mcp = FastMCP("PailFlow")


@mcp.tool()
def list_workflows() -> dict[str, Any]:
    """
    Returns available workflow names and descriptions.

    This tool lists all available PailFlow workflows that can be executed.
    Each workflow represents a complete action sequence that can orchestrate
    real-world outcomes.

    Returns:
        dict: A dictionary containing:
            - workflows: List of workflow objects with 'name' and 'description' fields
            - count: Total number of available workflows
    """
    try:
        workflows_dict = get_workflows()
        workflows_list = []

        # Convert workflows dict to list format
        for name, workflow in workflows_dict.items():
            workflows_list.append(
                {
                    "name": name,
                    "description": getattr(
                        workflow, "description", f"Workflow: {name}"
                    ),
                }
            )

        return {
            "workflows": workflows_list,
            "count": len(workflows_list),
        }
    except Exception as e:
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        return {
            "workflows": [],
            "count": 0,
            "error": str(e),
        }


@mcp.tool()
def execute_workflow(
    workflow_name: str,
    message: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """
    Executes a specific workflow with context.

    This tool runs a PailFlow workflow with the provided context information.
    Workflows can orchestrate complex sequences of actions to achieve real-world
    outcomes.

    Args:
        workflow_name: The name of the workflow to execute
        message: The message or input data for the workflow
        user_id: Optional user identifier for context
        channel_id: Optional channel identifier for context

    Returns:
        dict: A dictionary containing:
            - success: Boolean indicating if execution succeeded
            - result: The workflow execution result (if successful)
            - error: Error message (if execution failed)
    """
    try:
        logger.info(
            f"Executing workflow '{workflow_name}' with message: {message[:100]}..."
        )

        # Get the workflow
        workflow = get_workflow(workflow_name)

        # Execute the workflow with context
        # Note: This is a placeholder - actual execution will depend on workflow implementation
        result = workflow.execute(
            message=message, user_id=user_id, channel_id=channel_id
        )

        logger.info(f"Workflow '{workflow_name}' executed successfully")

        return {
            "success": True,
            "result": result,
            "workflow_name": workflow_name,
        }
    except WorkflowNotFoundError:
        logger.warning(f"Workflow not found: {workflow_name}")
        return {
            "success": False,
            "error": f"Workflow '{workflow_name}' not found",
            "workflow_name": workflow_name,
        }
    except NotImplementedError:
        logger.warning(f"Workflow not yet implemented: {workflow_name}")
        return {
            "success": False,
            "error": f"Workflow '{workflow_name}' is not yet implemented",
            "workflow_name": workflow_name,
        }
    except Exception as e:
        logger.error(f"Error executing workflow '{workflow_name}': {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "workflow_name": workflow_name,
        }


@mcp.tool()
def get_workflow_info(workflow_name: str) -> dict[str, Any]:
    """
    Returns detailed information about a workflow.

    This tool provides comprehensive information about a specific workflow,
    including its description, parameters, expected inputs, and outputs.

    Args:
        workflow_name: The name of the workflow to get information about

    Returns:
        dict: A dictionary containing:
            - name: The workflow name
            - description: Detailed description of the workflow
            - parameters: Expected parameters/inputs
            - outputs: Expected outputs/results
            - error: Error message if workflow not found
    """
    try:
        workflow = get_workflow(workflow_name)

        # Extract workflow information
        info = {
            "name": workflow_name,
            "description": getattr(workflow, "description", "No description available"),
            "parameters": getattr(workflow, "parameters", {}),
            "outputs": getattr(workflow, "outputs", {}),
        }

        # Add any additional metadata if available
        if hasattr(workflow, "metadata"):
            info["metadata"] = workflow.metadata

        return info
    except WorkflowNotFoundError:
        logger.warning(f"Workflow not found: {workflow_name}")
        return {
            "name": workflow_name,
            "error": f"Workflow '{workflow_name}' not found",
        }
    except NotImplementedError:
        logger.warning(f"Workflow not yet implemented: {workflow_name}")
        return {
            "name": workflow_name,
            "error": f"Workflow '{workflow_name}' is not yet implemented",
        }
    except Exception as e:
        logger.error(
            f"Error getting workflow info for '{workflow_name}': {e}", exc_info=True
        )
        return {
            "name": workflow_name,
            "error": str(e),
        }


class PailFlowMCPServer:
    """
    PailFlow MCP Server class.

    This class wraps the FastMCP server and provides methods to run it
    as an HTTP server using uvicorn.
    """

    def __init__(self):
        """Initialize the PailFlow MCP Server."""
        self.mcp = mcp
        logger.info("PailFlow MCP Server initialized")

    def run_http(self, host: str = "0.0.0.0", port: int = 8003) -> None:
        """
        Start the MCP server using uvicorn.

        This method starts the FastMCP server as an HTTP server that can be
        accessed by MCP clients. The server will listen on the specified host
        and port.

        Args:
            host: The host address to bind to (default: "0.0.0.0" for all interfaces)
            port: The port number to listen on (default: 8003)
        """
        logger.info(f"Starting PailFlow MCP Server on {host}:{port}")

        # Get the Starlette app from FastMCP for streamable HTTP transport
        app = self.mcp.streamable_http_app()

        # Run with uvicorn
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )


def main() -> None:
    """
    Main entry point for the PailFlow MCP Server.

    This function parses command line arguments for host and port configuration
    and starts the MCP server.
    """
    parser = argparse.ArgumentParser(
        description="PailFlow MCP Server - Exposes workflows as MCP tools"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8003,
        help="Port number to listen on (default: 8003)",
    )

    args = parser.parse_args()

    # Create and run the server
    server = PailFlowMCPServer()
    server.run_http(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
