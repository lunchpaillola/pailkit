# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Modal app for running bots in Modal Functions.

This module provides a Modal Function that wraps BotExecutor.run() logic,
allowing bots to run in Modal's serverless environment with fast startup
(~2-5s vs 30s with Fly machines) and better concurrency handling.
"""

import logging
import os
from typing import Any, Dict, Optional

import modal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create Modal app
app = modal.App("pailkit-bot")

# Get project root directory (one level up from flow/)
# modal_bot_runner.py is in flow/, so project root is parent directory
flow_dir = os.path.dirname(__file__)
project_root = os.path.dirname(flow_dir)

# Define image with Python 3.12 and all dependencies
# Read requirements.txt and install all dependencies
requirements_path = os.path.join(flow_dir, "requirements.txt")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .env({"PYTHONPATH": "/app"})
    .pip_install_from_requirements(requirements_path)
    # Copy flow/ and shared/ directories into the image
    # This matches the Dockerfile structure where code is copied to /app
    .add_local_dir(flow_dir, "/app/flow")
    .add_local_dir(os.path.join(project_root, "shared"), "/app/shared")
)

# Configure secrets - all API keys needed for bot execution
# Use modal.Secret.from_name() to reference secrets created in Modal dashboard
secrets = [
    modal.Secret.from_name("pailkit-secrets"),
]


@app.function(
    image=image,
    secrets=secrets,
    timeout=3600,  # 1 hour max bot runtime
    scaledown_window=600,  # Shutdown container after 10m of inactivity
    min_containers=1,  # Keep one warm container to reduce cold starts
)
async def run_bot(
    room_url: str,
    token: str,
    bot_config: Dict[str, Any],
    room_name: str,
    workflow_thread_id: Optional[str] = None,
) -> None:
    """
    Run a bot instance in a Modal Function.

    This function creates a BotExecutor instance and runs it with the provided
    parameters. It handles the complete bot lifecycle from start to finish.

    Args:
        room_url: Full Daily.co room URL
        token: Meeting token for authentication
        bot_config: Bot configuration dictionary
        room_name: Room name for saving transcript to database
        workflow_thread_id: Optional workflow thread ID to associate with this bot session

    Raises:
        Exception: If bot execution fails
    """
    try:
        logger.info(f"🚀 Starting bot in Modal Function for room: {room_name}")
        logger.info(f"   Room URL: {room_url}")
        logger.info(f"   Workflow thread ID: {workflow_thread_id}")

        # Import here to avoid import errors during Modal app definition
        from flow.steps.agent_call.bot.bot_executor import BotExecutor
        from flow.steps.agent_call.bot.result_processor import BotResultProcessor

        # Create minimal dependencies for standalone execution
        # For standalone execution, bot_config_map and bot_id_map can be empty
        # process_full_pipeline() will still work (it doesn't require these maps)
        result_processor = BotResultProcessor(
            bot_config_map={room_name: bot_config},  # Minimal map
            bot_id_map={},  # Empty - not needed for standalone
        )
        transport_map = {}  # Empty - will be populated by executor

        # Create executor instance
        executor = BotExecutor(
            result_processor=result_processor,
            transport_map=transport_map,
        )

        # Run the bot
        logger.info("✅ Bot executor created - starting bot execution...")
        await executor.run(
            room_url=room_url,
            token=token or "",
            bot_config=bot_config,
            room_name=room_name,
            workflow_thread_id=workflow_thread_id,
        )
        logger.info(f"✅ Bot execution completed for room: {room_name}")

    except Exception as e:
        logger.error(
            f"❌ Bot execution failed for room {room_name}: {e}", exc_info=True
        )
        raise
