# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Fly.io machine spawning for bot execution."""

import asyncio
import json
import logging
import os
import random
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

        # Retry configuration (configurable via environment variables)
        self.max_retries = int(os.getenv("FLY_MACHINE_SPAWN_MAX_RETRIES", "3"))
        self.initial_retry_delay = float(
            os.getenv("FLY_MACHINE_SPAWN_INITIAL_DELAY", "2.0")
        )
        self.max_retry_delay = float(os.getenv("FLY_MACHINE_SPAWN_MAX_DELAY", "30.0"))

    def _should_retry_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.

        Transient errors (retryable):
        - Network timeouts (httpx.TimeoutException)
        - Connection errors (httpx.RequestError)
        - Server errors (5xx status codes)
        - Rate limiting (429 status code)

        Permanent errors (not retryable):
        - Client errors (400, 401, 403, 404)
        - Configuration errors (RuntimeError)
        - Invalid requests

        Args:
            error: The exception to check

        Returns:
            True if the error is retryable, False otherwise
        """
        # Network/connection errors are always retryable
        if isinstance(error, (httpx.TimeoutException, httpx.RequestError)):
            return True

        # RuntimeError (configuration issues) should not be retried
        if isinstance(error, RuntimeError):
            return False

        # Check FlyMachineError for status codes
        if isinstance(error, FlyMachineError):
            status_code = error.status_code
            # Retry server errors (5xx) and rate limiting (429)
            if status_code >= 500 or status_code == 429:
                return True
            # Don't retry client errors (4xx, except 429)
            if 400 <= status_code < 500:
                return False

        # HTTPStatusError from httpx
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            # Retry server errors (5xx) and rate limiting (429)
            if status_code >= 500 or status_code == 429:
                return True
            # Don't retry client errors (4xx, except 429)
            if 400 <= status_code < 500:
                return False

        # For unknown errors, be conservative and don't retry
        return False

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
            timeout: Optional timeout in seconds for machine startup (default: 180 seconds)

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

        # Default timeout: 180 seconds (3 minutes) to allow for image pull and startup
        # Can be overridden via FLY_MACHINE_STARTUP_TIMEOUT environment variable
        if timeout is None:
            timeout = float(os.getenv("FLY_MACHINE_STARTUP_TIMEOUT", "180"))

        headers = {
            "Authorization": f"Bearer {self.fly_api_key}",
            "Content-Type": "application/json",
        }

        room_name = room_url.split("/")[-1]
        logger.info(
            f"🚀 Starting Fly.io machine spawn for room: {room_name} "
            f"(max retries: {self.max_retries})"
        )

        last_error = None

        # Retry loop with exponential backoff
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    logger.info(
                        f"🔄 Retry attempt {attempt}/{self.max_retries} for room: {room_name}"
                    )

                # Attempt to spawn the machine
                vm_id = await self._attempt_spawn(
                    room_url,
                    token,
                    bot_config,
                    workflow_thread_id,
                    timeout,
                    headers,
                    room_name,
                )

                # Success - return immediately
                logger.info(
                    f"✅ Machine spawn succeeded on attempt {attempt} for room: {room_name}"
                )
                return vm_id

            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self._should_retry_error(e):
                    # Non-retryable error - raise immediately
                    logger.error(
                        f"❌ Non-retryable error on attempt {attempt}/{self.max_retries} "
                        f"for room: {room_name}: {e}"
                    )
                    raise

                # Retryable error - check if we have retries left
                if attempt < self.max_retries:
                    # Calculate exponential backoff with jitter
                    base_delay = min(
                        self.initial_retry_delay * (2 ** (attempt - 1)),
                        self.max_retry_delay,
                    )
                    # Add jitter (0-20% of base delay) to prevent thundering herd
                    jitter = random.uniform(0, base_delay * 0.2)
                    delay = base_delay + jitter

                    error_type = type(e).__name__
                    error_msg = str(e)
                    if isinstance(e, FlyMachineError):
                        error_msg = f"{e.operation}: {e.message}"
                        if e.status_code:
                            error_msg += f" (status: {e.status_code})"

                    logger.warning(
                        f"⚠️ Retryable error on attempt {attempt}/{self.max_retries} "
                        f"for room: {room_name}: {error_type} - {error_msg}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    error_type = type(e).__name__
                    error_msg = str(e)
                    if isinstance(e, FlyMachineError):
                        error_msg = f"{e.operation}: {e.message}"
                        if e.status_code:
                            error_msg += f" (status: {e.status_code})"

                    logger.error(
                        f"❌ All {self.max_retries} retry attempts exhausted for room: {room_name}. "
                        f"Last error: {error_type} - {error_msg}"
                    )

        # If we get here, all retries were exhausted
        # Raise the last error
        if last_error:
            raise last_error
        else:
            # This shouldn't happen, but just in case
            raise FlyMachineError(
                operation="spawn",
                status_code=0,
                response_body="",
                message="All retry attempts exhausted without error",
            )

    async def _attempt_spawn(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        workflow_thread_id: Optional[str],
        timeout: float,
        headers: Dict[str, str],
        room_name: str,
    ) -> str:
        """
        Attempt to spawn a Fly.io machine (single attempt, no retries).

        This is the core spawn logic extracted for use in the retry loop.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            workflow_thread_id: Optional workflow thread ID
            timeout: Timeout in seconds for API requests
            headers: HTTP headers for Fly API requests
            room_name: Room name for logging

        Returns:
            Machine ID of the spawned machine

        Raises:
            FlyMachineError: If machine spawning fails
            httpx exceptions: For network/HTTP errors
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # Get the Docker image from the current app
                logger.info(
                    "📡 Fetching machine info from Fly API to determine Docker image..."
                )
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
                logger.debug(
                    "   Image will be pulled on machine startup (this may take 1-3 minutes)"
                )

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
                logger.info(
                    f"🔨 Creating Fly.io machine for bot (room: {room_name})... "
                    f"This includes image pull and machine initialization."
                )
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
                machine_data = res.json()
                vm_id = machine_data["id"]
                machine_state = machine_data.get("state", "unknown")
                logger.info(
                    f"✅ Machine created: {vm_id} (initial state: {machine_state})"
                )
                logger.debug(
                    f"   Machine will now pull image and start (monitored in background, "
                    f"timeout: {timeout}s)"
                )

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
        import time

        start_time = time.time()

        try:
            logger.info(
                f"⏳ [Background] Monitoring machine {vm_id} startup "
                f"(room: {room_name}, timeout: {timeout}s)..."
            )

            # Create a new client for the background task
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Poll machine status periodically to show progress
                poll_interval = 10.0  # Check status every 10 seconds
                last_state = None
                last_log_time = start_time

                try:
                    # Wait for the machine to enter the started state
                    # Use wait endpoint which blocks until state is reached
                    logger.debug(
                        f"[Background] Waiting for machine {vm_id} to reach 'started' state..."
                    )

                    # Start polling loop to show progress
                    while True:
                        elapsed = time.time() - start_time
                        if elapsed >= timeout:
                            break

                        # Check current machine state
                        try:
                            status_res = await client.get(
                                f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}",
                                headers=headers,
                            )
                            if status_res.status_code == 200:
                                machine_data = status_res.json()
                                current_state = machine_data.get("state", "unknown")

                                # Log state transitions
                                if current_state != last_state:
                                    elapsed_str = f"{elapsed:.1f}s"
                                    logger.info(
                                        f"🔄 [Background] Machine {vm_id} state transition: "
                                        f"{last_state or 'initial'} → {current_state} "
                                        f"(elapsed: {elapsed_str}, room: {room_name})"
                                    )
                                    last_state = current_state

                                    # Log additional context for specific states
                                    if current_state == "starting":
                                        logger.debug(
                                            "   [Background] Machine is starting (pulling image, initializing)..."
                                        )
                                    elif current_state == "started":
                                        elapsed_total = time.time() - start_time
                                        logger.info(
                                            f"✅ [Background] Machine {vm_id} is started and ready "
                                            f"(room: {room_name}, startup time: {elapsed_total:.1f}s)"
                                        )
                                        return

                                # Log progress every 30 seconds if still waiting
                                if time.time() - last_log_time >= 30.0:
                                    elapsed_str = f"{elapsed:.1f}s"
                                    logger.info(
                                        f"⏳ [Background] Machine {vm_id} still starting... "
                                        f"(current state: {current_state}, elapsed: {elapsed_str}, "
                                        f"room: {room_name})"
                                    )
                                    last_log_time = time.time()
                        except Exception as e:
                            logger.debug(
                                f"[Background] Error checking machine status: {e}"
                            )

                        # Wait a bit before next check, but also try the wait endpoint
                        # The wait endpoint is more efficient but we want progress updates
                        try:
                            wait_res = await asyncio.wait_for(
                                client.get(
                                    f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}/wait?state=started",
                                    headers=headers,
                                    timeout=poll_interval,
                                ),
                                timeout=poll_interval,
                            )
                            if wait_res.status_code == 200:
                                elapsed_total = time.time() - start_time
                                logger.info(
                                    f"✅ [Background] Machine {vm_id} is started and ready "
                                    f"(room: {room_name}, startup time: {elapsed_total:.1f}s)"
                                )
                                return
                        except asyncio.TimeoutError:
                            # Continue polling
                            continue
                        except Exception as e:
                            logger.debug(
                                f"[Background] Wait endpoint error (will continue polling): {e}"
                            )
                            await asyncio.sleep(poll_interval)

                    # If we get here, we've timed out
                    raise asyncio.TimeoutError()

                except asyncio.TimeoutError:
                    # Machine failed to start within timeout
                    elapsed_total = time.time() - start_time
                    error_msg = (
                        f"Machine {vm_id} failed to start within {timeout} seconds "
                        f"(elapsed: {elapsed_total:.1f}s)"
                    )
                    logger.warning(f"⚠️ [Background] {error_msg} (room: {room_name})")
                    # Try to get final machine status for more context
                    try:
                        status_res = await client.get(
                            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}",
                            headers=headers,
                        )
                        if status_res.status_code == 200:
                            machine_status = status_res.json()
                            final_state = machine_status.get("state", "unknown")
                            logger.warning(
                                f"   [Background] Machine {vm_id} final state: {final_state}"
                            )
                            # Log any error information if available
                            if "events" in machine_status:
                                recent_events = machine_status["events"][
                                    -3:
                                ]  # Last 3 events
                                for event in recent_events:
                                    if (
                                        event.get("type") == "exit"
                                        or "error" in event.get("type", "").lower()
                                    ):
                                        logger.warning(
                                            f"   [Background] Machine event: {event}"
                                        )
                    except Exception as e:
                        logger.debug(
                            f"[Background] Could not fetch final machine status: {e}"
                        )
                    # Don't raise - this is just for logging/observability
                    return

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
