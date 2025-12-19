# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Fly.io machine spawning for bot execution."""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class FlyMachineSpawner:
    """
    Handles spawning Fly.io machines to run bots.

    Simple Explanation: This class manages the creation of Fly.io machines
    that run bot instances. Each machine runs independently and auto-destroys
    when the bot finishes.
    """

    def __init__(
        self,
        fly_api_host: str,
        fly_app_name: str,
        fly_api_key: str,
    ):
        """
        Initialize the Fly.io machine spawner.

        Args:
            fly_api_host: Fly.io API host URL
            fly_app_name: Fly.io app name
            fly_api_key: Fly.io API key for authentication
        """
        self.fly_api_host = fly_api_host
        self.fly_app_name = fly_app_name
        self.fly_api_key = fly_api_key

    async def spawn(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        workflow_thread_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Spawn a new Fly.io machine to run the bot.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            workflow_thread_id: Optional workflow thread ID to associate with this bot session
            timeout: Optional timeout in seconds for machine startup (default: 60 seconds)

        Returns:
            Machine ID of the spawned machine

        Raises:
            RuntimeError: If Fly.io is not configured
            FlyMachineError: If machine spawning fails
            asyncio.TimeoutError: If machine startup times out
        """
        if not self.fly_api_key or not self.fly_app_name:
            raise RuntimeError(
                "Fly.io machine spawning is not enabled. "
                "Set FLY_API_KEY and FLY_APP_NAME environment variables."
            )

        # Default timeout: 60 seconds
        if timeout is None:
            timeout = float(os.getenv("FLY_MACHINE_STARTUP_TIMEOUT", "60"))

        headers = {
            "Authorization": f"Bearer {self.fly_api_key}",
            "Content-Type": "application/json",
        }

        room_name = room_url.split("/")[-1]
        logger.info(f"🚀 Starting Fly.io machine spawn for room: {room_name}")

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # Get the Docker image from the current app
                logger.debug("Fetching machine info from Fly API...")
                res = await client.get(
                    f"{self.fly_api_host}/apps/{self.fly_app_name}/machines",
                    headers=headers,
                )
                if res.status_code != 200:
                    error_msg = f"Unable to get machine info from Fly API (status {res.status_code})"
                    logger.error(f"❌ {error_msg}: {res.text}")
                    raise FlyMachineError(
                        operation="get_machine_info",
                        status_code=res.status_code,
                        response_body=res.text,
                        message=error_msg,
                    )

                machines = res.json()
                if not machines:
                    error_msg = "No machines found in Fly app to get image from"
                    logger.error(f"❌ {error_msg}")
                    raise FlyMachineError(
                        operation="get_machine_info",
                        status_code=200,
                        response_body="[]",
                        message=error_msg,
                    )

                image = machines[0]["config"]["image"]
                logger.info(f"📦 Using Docker image: {image}")

                # Prepare bot config as JSON for the command
                bot_config_json = json.dumps(bot_config)

                # Machine configuration
                cmd = [
                    "python3",
                    "flow/steps/agent_call/bot/bot_executor.py",
                    "-u",
                    room_url,
                    "-t",
                    token or "",  # Use empty string if token is None
                    "--bot-config",
                    bot_config_json,
                ]
                # Add workflow_thread_id if provided
                if workflow_thread_id:
                    cmd.extend(["--workflow-thread-id", workflow_thread_id])

                worker_props = {
                    "config": {
                        "image": image,
                        "auto_destroy": True,  # Machine destroys itself when bot exits
                        "init": {"cmd": cmd},
                        "restart": {
                            "policy": "no"
                        },  # Don't restart - let it exit cleanly
                        "guest": {
                            "cpu_kind": "shared",
                            "cpus": 1,
                            "memory_mb": 1024,  # 1GB RAM - enough for VAD and bot processing
                        },
                        "env": {
                            # Set PYTHONPATH so Python can find the flow module
                            "PYTHONPATH": "/app",
                            # Pass through required environment variables for bot execution
                            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                            "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", ""),
                            # Supabase credentials for saving workflow thread data and LangGraph checkpoints
                            # Support both SUPABASE_SERVICE_ROLE_KEY and SUPABASE_SECRET_KEY (modern naming)
                            "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
                            "SUPABASE_SERVICE_ROLE_KEY": os.getenv(
                                "SUPABASE_SERVICE_ROLE_KEY", ""
                            ),
                            "SUPABASE_SECRET_KEY": os.getenv("SUPABASE_SECRET_KEY", ""),
                            "SUPABASE_DB_PASSWORD": os.getenv(
                                "SUPABASE_DB_PASSWORD", ""
                            ),
                            # Note: DAILY_API_KEY is not needed - bot only joins rooms via WebSocket
                            # (room URL and optional token are passed as command args, not env vars)
                        },
                    },
                }

                # Spawn a new machine instance
                logger.info(f"🔨 Creating Fly.io machine for bot (room: {room_name})")
                res = await client.post(
                    f"{self.fly_api_host}/apps/{self.fly_app_name}/machines",
                    headers=headers,
                    json=worker_props,
                )

                if res.status_code != 200:
                    error_msg = (
                        f"Problem starting a bot worker (status {res.status_code})"
                    )
                    logger.error(f"❌ {error_msg}: {res.text}")
                    raise FlyMachineError(
                        operation="spawn_machine",
                        status_code=res.status_code,
                        response_body=res.text,
                        message=error_msg,
                    )

                # Get the machine ID from the response
                vm_id = res.json()["id"]
                logger.info(f"✅ Machine created: {vm_id}")

                # Start background task to monitor machine startup (non-blocking)
                # This allows the API to return immediately while the machine starts in the background
                asyncio.create_task(
                    self._monitor_machine_startup(vm_id, room_name, timeout, headers)
                )

                # Return immediately after machine creation - don't wait for startup
                # The machine will start and join the room in the background
                logger.info(
                    f"🚀 Machine {vm_id} created - starting in background (room: {room_name})"
                )
                return vm_id

            except httpx.TimeoutException as e:
                error_msg = f"Request to Fly API timed out after {timeout}s"
                logger.error(f"❌ {error_msg}: {e}")
                raise FlyMachineError(
                    operation="api_request",
                    status_code=408,
                    response_body=str(e),
                    message=error_msg,
                )
            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP error from Fly API: {e.response.status_code}"
                logger.error(f"❌ {error_msg}: {e.response.text}")
                raise FlyMachineError(
                    operation="api_request",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                    message=error_msg,
                )
            except httpx.RequestError as e:
                error_msg = f"Request error connecting to Fly API: {str(e)}"
                logger.error(f"❌ {error_msg}")
                raise FlyMachineError(
                    operation="api_request",
                    status_code=0,
                    response_body=str(e),
                    message=error_msg,
                )
            except FlyMachineError:
                # Re-raise our custom errors
                raise
            except Exception as e:
                error_msg = f"Unexpected error spawning Fly machine: {str(e)}"
                logger.error(f"❌ {error_msg}", exc_info=True)
                raise FlyMachineError(
                    operation="spawn",
                    status_code=0,
                    response_body=str(e),
                    message=error_msg,
                )

    async def _monitor_machine_startup(
        self,
        vm_id: str,
        room_name: str,
        timeout: float,
        headers: Dict[str, str],
    ) -> None:
        """
        Background task to monitor machine startup for logging/observability.

        This runs asynchronously and does not block the API response.
        It logs when the machine starts successfully or if it fails to start.

        Args:
            vm_id: Machine ID to monitor
            room_name: Room name for logging context
            timeout: Timeout in seconds for machine startup
            headers: HTTP headers for Fly API requests
        """
        try:
            logger.info(
                f"⏳ [Background] Monitoring machine {vm_id} startup (room: {room_name}, timeout: {timeout}s)..."
            )

            # Create a new client for the background task
            async with httpx.AsyncClient(timeout=timeout) as client:
                try:
                    # Wait for the machine to enter the started state
                    res = await asyncio.wait_for(
                        client.get(
                            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}/wait?state=started",
                            headers=headers,
                        ),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    # Machine failed to start within timeout
                    error_msg = (
                        f"Machine {vm_id} failed to start within {timeout} seconds"
                    )
                    logger.warning(f"⚠️ [Background] {error_msg} (room: {room_name})")
                    # Try to get machine status for more context
                    try:
                        status_res = await client.get(
                            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}",
                            headers=headers,
                        )
                        if status_res.status_code == 200:
                            machine_status = status_res.json()
                            logger.warning(
                                f"   [Background] Machine {vm_id} status: {machine_status.get('state', 'unknown')}"
                            )
                    except Exception as e:
                        logger.debug(
                            f"[Background] Could not fetch machine status: {e}"
                        )
                    # Don't raise - this is just for logging/observability
                    return

                if res.status_code != 200:
                    error_msg = f"Machine {vm_id} unable to enter started state (status {res.status_code})"
                    logger.warning(
                        f"⚠️ [Background] {error_msg} (room: {room_name}): {res.text}"
                    )
                    # Don't raise - this is just for logging/observability
                    return

                # Machine started successfully
                logger.info(
                    f"✅ [Background] Machine {vm_id} is started and ready (room: {room_name})"
                )

        except Exception as e:
            # Log but don't raise - this is a background monitoring task
            logger.warning(
                f"⚠️ [Background] Error monitoring machine {vm_id} startup (room: {room_name}): {e}",
                exc_info=True,
            )


class FlyMachineError(Exception):
    """
    Custom exception for Fly machine operations with detailed error context.
    """

    def __init__(
        self,
        operation: str,
        message: str,
        status_code: int = 0,
        response_body: str = "",
        machine_id: Optional[str] = None,
    ):
        """
        Initialize Fly machine error.

        Args:
            operation: The operation that failed (e.g., "spawn_machine", "wait_for_started")
            message: Human-readable error message
            status_code: HTTP status code from Fly API (0 if not applicable)
            response_body: Response body from Fly API
            machine_id: Machine ID if machine was created before failure
        """
        self.operation = operation
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.machine_id = machine_id
        super().__init__(self.message)

    def __str__(self) -> str:
        """Format error message with context."""
        parts = [f"FlyMachineError: {self.message}"]
        parts.append(f"  Operation: {self.operation}")
        if self.machine_id:
            parts.append(f"  Machine ID: {self.machine_id}")
        else:
            parts.append("  Machine ID: (not created)")
        if self.status_code:
            parts.append(f"  HTTP Status: {self.status_code}")
        if self.response_body:
            # Truncate long response bodies
            body = (
                self.response_body[:200] + "..."
                if len(self.response_body) > 200
                else self.response_body
            )
            parts.append(f"  Response: {body}")
        return "\n".join(parts)
