# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Pipecat Bot Service - AI bot that joins Daily meetings."""

import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pipecat.transports.daily.transport import DailyTransport

from flow.steps.agent_call.bot.animation import TalkingAnimation
from flow.steps.agent_call.bot.bot_executor import BotExecutor
from flow.steps.agent_call.bot.bot_process import BotProcess
from flow.steps.agent_call.bot.fly_machine import FlyMachineSpawner
from flow.steps.agent_call.bot.result_processor import BotResultProcessor
from flow.steps.agent_call.bot.speaker_tracking import SpeakerTrackingProcessor
from flow.steps.agent_call.bot.transcript_handler import TranscriptHandler
from flow.steps.agent_call.bot.video_frames import load_bot_video_frames

logger = logging.getLogger(__name__)

# Re-export classes for backward compatibility
# These are imported from separate modules but exported here so existing imports still work
__all__ = [
    "BotService",
    "bot_service",
    "BotProcess",
    "TranscriptHandler",
    "SpeakerTrackingProcessor",
    "TalkingAnimation",
    "load_bot_video_frames",
]

# Note: "Event loop is closed" RuntimeErrors may appear in logs when the bot finishes.
# These come from Daily.co transport's WebSocket callbacks trying to post to a closed loop.
# They are harmless and expected during cleanup - the bot still functions correctly.


class ModalBotSpawner:
    """
    Handles spawning Modal Functions to run bots.

    Simple Explanation: This class manages calling Modal Functions
    that run bot instances. Each function runs independently and
    auto-cleans up when the bot finishes.
    """

    def __init__(self):
        """Initialize the Modal bot spawner."""
        try:
            import modal

            self.modal = modal
        except ImportError:
            raise RuntimeError(
                "Modal is not installed. Install with: pip install modal>=0.60"
            )
        self.app_name = os.getenv("MODAL_APP_NAME", "pailkit-bot")
        self.function_name = os.getenv("MODAL_FUNCTION_NAME", "run_bot")
        if not self.app_name or not self.function_name:
            raise RuntimeError(
                "Modal app/function names must be configured (MODAL_APP_NAME, MODAL_FUNCTION_NAME)."
            )

    async def spawn(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        workflow_thread_id: Optional[str] = None,
    ) -> str:
        """
        Spawn a Modal Function to run the bot.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            workflow_thread_id: Optional workflow thread ID to associate with this bot session

        Returns:
            Function call ID (string identifier)

        Raises:
            RuntimeError: If Modal is not configured
            Exception: If function call fails
        """
        try:
            logger.info(
                "🚀 Calling Modal function for room %s (app=%s, function=%s)",
                room_url.split("/")[-1],
                self.app_name,
                self.function_name,
            )

            run_bot_func = None
            lookup_errors: list[Exception] = []

            # Try modern lookup first
            try:
                run_bot_func = self.modal.Function.from_name(
                    self.app_name, self.function_name
                )
            except Exception as e_from_name:
                lookup_errors.append(e_from_name)
                # Fallback to lookup API (older clients)
                try:
                    run_bot_func = self.modal.Function.lookup(
                        self.function_name, app=self.app_name
                    )
                except Exception as e_lookup:
                    lookup_errors.append(e_lookup)

            if run_bot_func is None:
                raise RuntimeError(
                    f"Unable to find Modal function {self.function_name} in app {self.app_name}: "
                    + "; ".join(str(e) for e in lookup_errors)
                )

            call_handle = run_bot_func.spawn(
                room_url=room_url,
                token=token or "",
                bot_config=bot_config,
                room_name=room_url.split("/")[-1],
                workflow_thread_id=workflow_thread_id,
            )

            call_id = (
                getattr(call_handle, "object_id", None)
                or getattr(call_handle, "function_call_id", None)
                or str(call_handle)
            )

            logger.info(
                "✅ Modal function called successfully (call_id: %s) for room: %s",
                call_id,
                room_url.split("/")[-1],
            )

            return str(call_id)

        except Exception as e:
            error_msg = f"Failed to call Modal function: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            raise RuntimeError(error_msg)

    def is_call_running(self, call_id: str) -> bool:
        """Check Modal function call status by ID."""
        if not call_id:
            return False

        try:
            func_call = self.modal.FunctionCall.from_id(call_id)
        except Exception as e:
            logger.warning(
                "⚠️ Could not retrieve Modal function call %s: %s", call_id, e
            )
            return False

        try:
            # If get() returns without Timeout, the call is complete
            func_call.get(timeout=0)
            return False
        except self.modal.exception.TimeoutError:
            return True
        except TimeoutError:
            return True
        except self.modal.exception.OutputExpiredError:
            # Output expired -> finished/not running
            return False
        except self.modal.exception.FunctionCallNotFoundError:
            return False
        except Exception as e:
            logger.warning(
                "⚠️ Error checking Modal function call %s status: %s", call_id, e
            )
            return False


class BotService:
    """Service to manage Pipecat bot instances with proper process management."""

    def __init__(self):
        self.active_bots: Dict[str, BotProcess] = {}
        self._shutdown_event = asyncio.Event()
        self._start_lock = (
            asyncio.Lock()
        )  # Lock to prevent race conditions when starting bots
        # Simple Explanation: bot_id_map tracks which bot_id is associated with each room_name
        # This allows us to update bot session records when the bot finishes
        self.bot_id_map: Dict[str, str] = {}
        # Simple Explanation: bot_config_map stores bot configuration for each room
        # This includes whether to process insights after the bot finishes
        self.bot_config_map: Dict[str, Dict[str, Any]] = {}
        # Simple Explanation: transport_map stores DailyTransport instances for each room
        # This allows us to explicitly leave the room during cleanup
        self.transport_map: Dict[str, "DailyTransport"] = {}
        # Track Modal function call IDs by room for status checks
        self.modal_call_map: Dict[str, str] = {}
        # Track Fly machine IDs by room for status checks
        self.fly_machine_map: Dict[str, str] = {}

        # Fly.io configuration - read from environment variables
        fly_api_host = os.getenv("FLY_API_HOST", "https://api.machines.dev/v1")
        fly_app_name = os.getenv("FLY_APP_NAME", "")
        fly_api_key = os.getenv("FLY_API_KEY", "")
        self.use_fly_machines = bool(fly_api_key and fly_app_name)

        # Modal configuration - read from environment variable
        self.use_modal_bots = os.getenv("USE_MODAL_BOTS", "false").lower() == "true"

        # Initialize Fly.io machine spawner if enabled
        if self.use_fly_machines:
            self.fly_spawner = FlyMachineSpawner(
                fly_api_host=fly_api_host,
                fly_app_name=fly_app_name,
                fly_api_key=fly_api_key,
            )
            logger.info(f"✅ Fly.io machine spawning enabled (app: {fly_app_name})")
        else:
            self.fly_spawner = None
            logger.info(
                "ℹ️ Fly.io machine spawning disabled - using direct execution. "
                "Set FLY_API_KEY and FLY_APP_NAME to enable."
            )

        # Initialize Modal spawner if enabled
        if self.use_modal_bots:
            try:
                self.modal_spawner = ModalBotSpawner()
                logger.info("✅ Modal bot spawning enabled")
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed to initialize Modal spawner: {e} - falling back to other methods"
                )
                self.modal_spawner = None
                self.use_modal_bots = False
        else:
            self.modal_spawner = None

        # Initialize result processor
        self.result_processor = BotResultProcessor(
            bot_config_map=self.bot_config_map,
            bot_id_map=self.bot_id_map,
        )

        # Initialize bot executor
        self.bot_executor = BotExecutor(
            result_processor=self.result_processor,
            transport_map=self.transport_map,
        )

    async def start_bot(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        room_name: Optional[str] = None,
        use_fly_machines: Optional[bool] = None,
        bot_id: Optional[str] = None,
        workflow_thread_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Start a bot instance for the given room.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            room_name: Optional room name (extracted from URL if not provided)
            use_fly_machines: Whether to use Fly.io machines (None = auto-detect from config)
            bot_id: Optional bot ID for tracking
            workflow_thread_id: Optional workflow thread ID to associate with this bot session

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
            If success is False, error_message contains the error details.
        """
        try:
            if not room_name:
                room_name = room_url.split("/")[-1]

            # Determine whether to use Fly.io machines
            should_use_fly = (
                use_fly_machines
                if use_fly_machines is not None
                else self.use_fly_machines
            )

            # Use a lock to prevent race conditions - ensure only one bot starts per room
            async with self._start_lock:
                # Double-check after acquiring lock (another request might have started it)
                if (
                    room_name in self.active_bots
                    and self.active_bots[room_name].is_running
                ):
                    logger.warning(f"Bot already running for room: {room_name}")
                    return True, None

                # Check if Modal should be used (before Fly check)
                if self.use_modal_bots:
                    # Spawn a Modal Function for the bot
                    if not self.modal_spawner:
                        logger.warning(
                            "Modal spawner not initialized - falling back to Fly machines or direct execution"
                        )
                    else:
                        try:
                            call_id = await self.modal_spawner.spawn(
                                room_url, token, bot_config, workflow_thread_id
                            )
                            logger.info(
                                f"✅ Bot spawned on Modal (call_id: {call_id}) for room {room_name}"
                            )
                            # Track Modal call ID for status checks
                            self.modal_call_map[room_name] = str(call_id)
                            # For Modal functions, we don't track them in active_bots
                            # because they run independently and auto-cleanup when done
                            return True, None
                        except Exception as e:
                            error_message = f"Modal function call failed: {str(e)}"
                            logger.error(f"❌ {error_message}", exc_info=True)
                            # Fall back to Fly machines or direct execution
                            logger.info(
                                "Falling back to Fly machines or direct execution..."
                            )
                            # Continue to next execution path (don't return False yet)

                if should_use_fly:
                    # Spawn a Fly.io machine for the bot
                    if not self.fly_spawner:
                        logger.warning(
                            "Fly.io spawner not initialized - falling back to direct execution"
                        )
                        should_use_fly = False
                    else:
                        try:
                            vm_id = await self.fly_spawner.spawn(
                                room_url, token, bot_config, workflow_thread_id
                            )
                            logger.info(
                                f"✅ Bot spawned on Fly.io machine {vm_id} for room {room_name}"
                            )
                            # Track Fly machine ID for status checks
                            self.fly_machine_map[room_name] = vm_id
                            # For Fly.io machines, we don't track them in active_bots
                            # because they run independently and auto-destroy when done
                            return True, None
                        except Exception as e:
                            # Import here to avoid circular dependency
                            from flow.steps.agent_call.bot.fly_machine import (
                                FlyMachineError,
                            )

                            error_message = None
                            if isinstance(e, FlyMachineError):
                                error_message = f"Fly.io machine spawn failed: {e.operation} - {e.message}"
                                if e.machine_id:
                                    error_message += f" (machine_id: {e.machine_id})"
                                logger.error(
                                    f"❌ {error_message}",
                                    extra={
                                        "machine_id": e.machine_id,
                                        "status_code": e.status_code,
                                        "operation": e.operation,
                                    },
                                )
                            else:
                                error_message = (
                                    f"Failed to spawn Fly.io machine: {str(e)}"
                                )
                                logger.error(f"❌ {error_message}", exc_info=True)
                            # Fall back to direct execution if Fly.io fails
                            logger.info("Falling back to direct execution...")
                            should_use_fly = False
                            # Return error message so workflow can use it
                            # But we'll still try direct execution, so don't return False yet

                if not should_use_fly:
                    # Direct execution: run bot in current process
                    # Simple Explanation: Store bot_id and config for this room so we can
                    # process results when the bot finishes
                    if bot_id:
                        self.bot_id_map[room_name] = bot_id
                    self.bot_config_map[room_name] = bot_config

                    bot_task = asyncio.create_task(
                        self.bot_executor.run(
                            room_url, token, bot_config, room_name, workflow_thread_id
                        )
                    )

                    # Track the bot BEFORE it starts running (so concurrent requests see it)
                    bot_process = BotProcess(room_name, bot_task)
                    self.active_bots[room_name] = bot_process

                    # Set up cleanup callback
                    bot_task.add_done_callback(lambda t: self._cleanup_bot(room_name))

                    logger.info(
                        f"Started bot for room {room_name} (ID: {bot_process.process_id})"
                    )

                    # Give the bot task a moment to start and check if it's still running
                    await asyncio.sleep(0.1)  # Small delay to let task start
                    if bot_task.done():
                        # Task finished immediately - something went wrong
                        try:
                            await bot_task  # This will raise the exception if there was one
                        except Exception as e:
                            error_msg = f"Bot task failed immediately: {str(e)}"
                            logger.error(f"❌ {error_msg}", exc_info=True)
                            return False, error_msg
                    else:
                        logger.info("✅ Bot task is running (not done yet)")

                return True, None

        except Exception as e:
            error_msg = f"Failed to start bot: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def _cleanup_bot(self, room_name: str) -> None:
        """Clean up a bot that has finished."""
        if room_name in self.active_bots:
            bot_process = self.active_bots[room_name]
            runtime_hours = bot_process.runtime_seconds / 3600

            # Log warning if bot ran for a long time
            if runtime_hours > 1:
                logger.warning(
                    f"⚠️ Bot for room {room_name} ran for {runtime_hours:.2f} hours "
                    f"({bot_process.runtime_seconds:.1f}s) - this is longer than expected"
                )

            logger.info(
                f"Cleaning up bot for room {room_name} (ran for {runtime_hours:.2f} hours)"
            )
            del self.active_bots[room_name]

            # Clean up bot_id and config mappings
            # Simple Explanation: Remove the bot_id and config from our tracking maps
            # since the bot is done and we've processed the results
            if room_name in self.bot_id_map:
                del self.bot_id_map[room_name]
            if room_name in self.bot_config_map:
                del self.bot_config_map[room_name]
            if room_name in self.modal_call_map:
                del self.modal_call_map[room_name]
            if room_name in self.fly_machine_map:
                del self.fly_machine_map[room_name]

    async def stop_bot(self, room_name: str) -> bool:
        """Stop a bot instance for the given room."""
        try:
            if room_name not in self.active_bots:
                logger.warning(f"No bot running for room: {room_name}")
                return False

            bot_process = self.active_bots[room_name]

            if not bot_process.is_running:
                logger.info(f"Bot for room {room_name} already stopped")
                del self.active_bots[room_name]
                return True

            # Cancel the task
            bot_process.task.cancel()

            try:
                await bot_process.task
            except asyncio.CancelledError:
                pass

            logger.info(f"Stopped bot for room: {room_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop bot: {e}", exc_info=True)
            return False

    def is_bot_running(self, room_name: str) -> bool:
        """Check if a bot is running for the given room."""
        # Check Modal function call status first
        call_id = self.modal_call_map.get(room_name)
        if call_id:
            if self.modal_spawner:
                try:
                    if self.modal_spawner.is_call_running(call_id):
                        return True
                except Exception as e:
                    logger.warning(
                        "⚠️ Error checking Modal status for room %s (call_id=%s): %s",
                        room_name,
                        call_id,
                        e,
                    )
            # Clean up stale entry if not running
            self.modal_call_map.pop(room_name, None)

        # Check in-process bot tasks
        if room_name in self.active_bots:
            return self.active_bots[room_name].is_running

        # Check Fly machine status if tracked
        vm_id = self.fly_machine_map.get(room_name)
        if vm_id and self.fly_spawner:
            try:
                if self.fly_spawner.is_machine_running(vm_id):
                    return True
            except Exception as e:
                logger.warning(
                    "⚠️ Error checking Fly machine status for room %s (vm_id=%s): %s",
                    room_name,
                    vm_id,
                    e,
                )
            # Clean up stale entry if not running
            self.fly_machine_map.pop(room_name, None)

        return False

    def get_bot_status(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed status of a bot."""
        if room_name not in self.active_bots:
            return None

        bot_process = self.active_bots[room_name]
        return {
            "room_name": room_name,
            "process_id": bot_process.process_id,
            "is_running": bot_process.is_running,
            "runtime_seconds": bot_process.runtime_seconds,
        }

    def list_active_bots(self) -> Dict[str, Dict[str, Any]]:
        """List all active bots with their status."""
        result = {}
        for room_name in self.active_bots:
            status = self.get_bot_status(room_name)
            if status is not None:
                # Add warning flag if bot has been running too long
                runtime_hours = status.get("runtime_seconds", 0) / 3600
                status["runtime_hours"] = runtime_hours
                if runtime_hours > 1:
                    status["warning"] = (
                        f"Bot has been running for {runtime_hours:.2f} hours"
                    )
                result[room_name] = status
        return result

    async def cleanup_long_running_bots(self, max_hours: float = 2.0) -> int:
        """
        Clean up bots that have been running longer than max_hours.

        This is a safety mechanism to prevent bots running forever.

        Args:
            max_hours: Maximum hours a bot should run (default: 2 hours)

        Returns:
            Number of bots stopped
        """
        stopped_count = 0
        max_seconds = max_hours * 3600

        for room_name, bot_process in list(self.active_bots.items()):
            if bot_process.is_running:
                runtime = bot_process.runtime_seconds
                if runtime > max_seconds:
                    logger.warning(
                        f"⚠️ Stopping long-running bot: {room_name} "
                        f"(ran for {runtime / 3600:.2f} hours, max: {max_hours}h)"
                    )
                    await self.stop_bot(room_name)
                    stopped_count += 1

        if stopped_count > 0:
            logger.info(f"Cleaned up {stopped_count} long-running bot(s)")

        return stopped_count

    async def cleanup(self) -> None:
        """Stop all running bots and ensure they leave the room."""
        logger.info(f"Cleaning up {len(self.active_bots)} bots...")

        # First, try to explicitly leave the room for each bot before cancelling
        # This ensures the bot leaves the Daily.co room even if cancellation is abrupt
        # Simple Explanation: We need to clean up transports BEFORE cancelling tasks to prevent
        # Rust panics. The audio renderer threads need time to finish before Python shuts down.
        for room_name, bot_process in list(self.active_bots.items()):
            transport = self.transport_map.get(room_name)
            if transport and bot_process.is_running:
                try:
                    logger.info(
                        f"🚪 Explicitly leaving Daily.co room before cancellation: {room_name}"
                    )
                    # Give a short timeout to leave the room
                    await asyncio.wait_for(transport.cleanup(), timeout=2.0)
                    logger.info(f"✅ Successfully left room: {room_name}")

                    # Critical: Add delay to allow audio renderer threads to finish
                    # Simple Explanation: The Rust audio renderer thread needs time to clean up
                    # before Python interpreter shuts down. Without this delay, the Rust thread
                    # tries to use Python APIs during shutdown, causing a panic.
                    logger.info("⏳ Waiting for audio renderer threads to finish...")
                    await asyncio.sleep(1.5)  # Wait 1.5 seconds for threads to finish
                    logger.info("✅ Delay completed - threads should be finished")
                except asyncio.TimeoutError:
                    logger.warning(
                        f"⚠️ Timeout leaving room {room_name}, proceeding with cancellation"
                    )
                except (RuntimeError, asyncio.CancelledError) as e:
                    # Ignore "Event loop is closed" errors - these are expected during shutdown
                    if "Event loop is closed" not in str(e):
                        logger.debug(f"Error leaving room {room_name}: {e}")
                except Exception as e:
                    # Catch and log Rust panics during shutdown - don't crash on them
                    # Simple Explanation: Rust panics can occur if audio renderer threads
                    # are still running during shutdown. We log them but don't fail.
                    error_msg = str(e)
                    if "panic" in error_msg.lower() or "rust" in error_msg.lower():
                        logger.warning(
                            f"⚠️ Rust panic during shutdown (non-fatal) for room {room_name}: {e}"
                        )
                    else:
                        logger.warning(f"Error leaving room {room_name}: {e}")

        # Add a final delay after all transport cleanups to ensure all threads finish
        # Simple Explanation: Even after individual transport cleanups, we add one more
        # delay to ensure all audio renderer threads across all bots have finished
        # before we proceed with task cancellation.
        if self.transport_map:
            logger.info("⏳ Final delay to ensure all threads have finished...")
            await asyncio.sleep(0.5)  # Additional 0.5 seconds for any remaining threads
            logger.info("✅ Final delay completed")

        # Cancel all bot tasks
        for room_name, bot_process in self.active_bots.items():
            if bot_process.is_running:
                logger.info(f"🛑 Cancelling bot task for room: {room_name}")
                bot_process.task.cancel()

        # Wait for all tasks to complete (with a timeout to prevent hanging)
        if self.active_bots:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *[
                            bot_process.task
                            for bot_process in self.active_bots.values()
                        ],
                        return_exceptions=True,
                    ),
                    timeout=5.0,  # Give tasks 5 seconds to complete cleanup
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "⚠️ Timeout waiting for bot tasks to complete, proceeding with cleanup"
                )

        self.active_bots.clear()
        self.transport_map.clear()  # Clear transport map
        logger.info("All bots cleaned up")

    @asynccontextmanager
    async def managed_bot(self, room_url: str, token: str, bot_config: Dict[str, Any]):
        """Context manager for a managed bot lifecycle."""
        room_name = room_url.split("/")[-1]

        try:
            success, error_msg = await self.start_bot(room_url, token, bot_config)
            if not success:
                error_message = error_msg or "Failed to start bot"
                raise RuntimeError(
                    f"Failed to start bot for room {room_name}: {error_message}"
                )

            yield self.get_bot_status(room_name)

        finally:
            await self.stop_bot(room_name)


# Global bot service instance
bot_service = BotService()


# Register cleanup on shutdown
def _setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating cleanup...")
        try:
            # Try to get the current event loop
            loop = asyncio.get_running_loop()
            # Schedule cleanup task - the cleanup() method will explicitly leave rooms
            # before cancelling tasks, which should ensure bots leave properly
            loop.create_task(bot_service.cleanup())
            logger.info(
                "Cleanup task scheduled - bots will leave rooms before shutdown"
            )
            # Note: We can't easily wait for the task here since we're in a signal handler,
            # but the cleanup() method now explicitly leaves rooms before cancelling,
            # which should ensure proper cleanup even if the process exits quickly
        except RuntimeError:
            # No event loop running - can't do async cleanup
            # This shouldn't happen in normal operation, but handle it gracefully
            logger.warning(
                "No event loop available for cleanup - bots may not leave rooms properly"
            )
            # Try to run cleanup in a new event loop as a last resort
            try:
                asyncio.run(bot_service.cleanup())
            except Exception as e:
                logger.error(f"Failed to run cleanup: {e}")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


_setup_signal_handlers()
