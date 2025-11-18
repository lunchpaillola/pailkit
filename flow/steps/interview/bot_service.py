# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Pipecat Bot Service - AI bot that joins Daily meetings."""

import asyncio
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
    LocalSmartTurnAnalyzerV3,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

logger = logging.getLogger(__name__)


class BotProcess:
    """Represents a single bot process with proper lifecycle management."""

    def __init__(self, room_name: str, task: asyncio.Task):
        self.room_name = room_name
        self.task = task
        self.process_id = str(uuid.uuid4())
        self.start_time = asyncio.get_event_loop().time()

    @property
    def is_running(self) -> bool:
        """Check if the bot task is still running."""
        return not self.task.done()

    @property
    def runtime_seconds(self) -> float:
        """Get how long the bot has been running."""
        return asyncio.get_event_loop().time() - self.start_time


class BotService:
    """Service to manage Pipecat bot instances with proper process management."""

    def __init__(self):
        self.active_bots: Dict[str, BotProcess] = {}
        self._shutdown_event = asyncio.Event()
        self._start_lock = (
            asyncio.Lock()
        )  # Lock to prevent race conditions when starting bots

    async def start_bot(
        self, room_url: str, token: str, bot_config: Dict[str, Any]
    ) -> bool:
        """Start a bot instance for the given room."""
        try:
            room_name = room_url.split("/")[-1]

            # Use a lock to prevent race conditions - ensure only one bot starts per room
            async with self._start_lock:
                # Double-check after acquiring lock (another request might have started it)
                if (
                    room_name in self.active_bots
                    and self.active_bots[room_name].is_running
                ):
                    logger.warning(f"Bot already running for room: {room_name}")
                    return True

                # Create bot task
                bot_task = asyncio.create_task(
                    self._run_bot(room_url, token, bot_config)
                )

                # Track the bot BEFORE it starts running (so concurrent requests see it)
                bot_process = BotProcess(room_name, bot_task)
                self.active_bots[room_name] = bot_process

                # Set up cleanup callback
                bot_task.add_done_callback(lambda t: self._cleanup_bot(room_name))

                logger.info(
                    f"Started bot for room {room_name} (ID: {bot_process.process_id})"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to start bot: {e}", exc_info=True)
            return False

    async def _run_bot(
        self, room_url: str, token: str, bot_config: Dict[str, Any]
    ) -> None:
        """Run the Pipecat bot directly without subprocess."""
        # **CRITICAL SAFEGUARDS:**
        # - Maximum runtime: 2 hours (prevents bots running forever)
        # - Idle timeout: 10 minutes (stop if no one joins)
        MAX_RUNTIME_SECONDS = 2 * 60 * 60  # 2 hours maximum
        IDLE_TIMEOUT_SECONDS = 10 * 60  # 10 minutes - stop if no one joins

        participant_joined_event = asyncio.Event()

        try:

            system_message = bot_config.get(
                "system_message",
                "You are a helpful AI assistant in a video call. Your goal is to helpful and engaging. "
                "Your output will be spoken aloud, so avoid special characters that can't easily be spoken, "
                "such as emojis or bullet points. Respond to what the user says in a creative and helpful way.",
            )

            bot_name = bot_config.get("name", "PailBot")

            transport = DailyTransport(
                room_url,
                token,
                bot_name,
                DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    transcription_enabled=True,
                    vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
                    turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams()),
                ),
            )

            logger.info(
                f"Bot transport initialized for room: {room_url}, bot_name: {bot_name}"
            )

            # Use OpenAI for both LLM and TTS
            llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")
            tts = OpenAITTSService(api_key=os.getenv("OPENAI_API_KEY"), voice="alloy")

            messages = [
                {
                    "role": "system",
                    "content": system_message,
                },
            ]

            context = LLMContext(messages)
            context_aggregator = LLMContextAggregatorPair(context)

            pipeline = Pipeline(
                [
                    transport.input(),  # Transport user input
                    context_aggregator.user(),  # User responses
                    llm,  # LLM
                    tts,  # TTS
                    transport.output(),  # Transport bot output
                    context_aggregator.assistant(),  # Assistant spoken responses
                ]
            )

            task = PipelineTask(
                pipeline,
                params=PipelineParams(
                    enable_metrics=True,
                    enable_usage_metrics=True,
                ),
            )

            @transport.event_handler("on_participant_joined")
            async def on_participant_joined(transport, participant):
                """Log when any participant (including bot) joins."""
                logger.info(
                    f"Participant joined room: {participant.get('id', 'unknown')}"
                )

            @transport.event_handler("on_first_participant_joined")
            async def on_first_participant_joined(transport, participant):
                logger.info(f"First participant joined: {participant['id']}")
                participant_joined_event.set()  # Mark that someone joined
                await transport.capture_participant_transcription(participant["id"])
                logger.info(
                    f"Started capturing transcription for participant: {participant['id']}"
                )
                # Kick off the conversation.
                messages.append(
                    {
                        "role": "system",
                        "content": "Please introduce yourself to the user.",
                    }
                )
                await task.queue_frames([LLMRunFrame()])

            @transport.event_handler("on_transcription_message")
            async def on_transcription_message(transport, message):
                """Log when transcription messages are received from users."""
                participant_id = message.get("participant_id", "unknown")
                text = message.get("text", "")
                is_final = message.get("is_final", False)
                logger.info(
                    f"Transcription received - Participant: {participant_id}, "
                    f"Text: '{text}', Final: {is_final}"
                )

            @transport.event_handler("on_transcription_error")
            async def on_transcription_error(transport, error):
                """Log transcription errors."""
                logger.error(f"Transcription error: {error}")

            @transport.event_handler("on_participant_left")
            async def on_participant_left(transport, participant, reason):
                logger.info(f"Participant left: {participant['id']}, reason: {reason}")
                await task.cancel()

            runner = PipelineRunner()

            logger.info("Starting bot pipeline runner...")

            # Start the runner in the background so the transport can connect
            # The runner needs to be running for the transport to connect and detect participants
            runner_task = asyncio.create_task(runner.run(task))

            # **SAFEGUARD 1: Wait for participant with idle timeout**
            # If no one joins within IDLE_TIMEOUT_SECONDS, stop the bot
            # NOTE: We wait AFTER starting the runner because the transport needs to be
            # running to connect to Daily and detect when participants join
            try:
                logger.info(
                    f"Waiting for participant to join (timeout: {IDLE_TIMEOUT_SECONDS}s)..."
                )
                await asyncio.wait_for(
                    participant_joined_event.wait(), timeout=IDLE_TIMEOUT_SECONDS
                )
                logger.info("Participant joined, bot is active")
            except asyncio.TimeoutError:
                logger.warning(
                    f"No participants joined within {IDLE_TIMEOUT_SECONDS}s, stopping bot"
                )
                await task.cancel()
                # Wait for runner to finish cancelling
                try:
                    await runner_task
                except (asyncio.CancelledError, Exception):
                    pass
                return

            # **SAFEGUARD 2: Maximum runtime timeout**
            # Wait for the runner task to complete, with a maximum runtime limit
            try:
                await asyncio.wait_for(runner_task, timeout=MAX_RUNTIME_SECONDS)
                logger.info("Bot pipeline runner finished normally")
            except asyncio.TimeoutError:
                logger.error(
                    f"Bot exceeded maximum runtime of {MAX_RUNTIME_SECONDS}s ({MAX_RUNTIME_SECONDS/3600:.1f} hours), forcing shutdown"
                )
                await task.cancel()
                # Wait for runner to finish cancelling
                try:
                    await runner_task
                except (asyncio.CancelledError, Exception):
                    pass
                # Log warning for monitoring
                logger.warning(
                    f"⚠️ FORCED SHUTDOWN: Bot for room {room_url.split('/')[-1]} "
                    f"ran for {MAX_RUNTIME_SECONDS/3600:.1f} hours and was stopped"
                )
            except asyncio.CancelledError:
                logger.info("Bot pipeline runner cancelled")
                raise

        except Exception as e:
            logger.error(f"Bot process error: {e}", exc_info=True)
            raise

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
        if room_name not in self.active_bots:
            return False

        return self.active_bots[room_name].is_running

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
                        f"(ran for {runtime/3600:.2f} hours, max: {max_hours}h)"
                    )
                    await self.stop_bot(room_name)
                    stopped_count += 1

        if stopped_count > 0:
            logger.info(f"Cleaned up {stopped_count} long-running bot(s)")

        return stopped_count

    async def cleanup(self) -> None:
        """Stop all running bots."""
        logger.info(f"Cleaning up {len(self.active_bots)} bots...")

        # Cancel all bot tasks
        for room_name, bot_process in self.active_bots.items():
            if bot_process.is_running:
                bot_process.task.cancel()

        # Wait for all tasks to complete
        if self.active_bots:
            await asyncio.gather(
                *[bot_process.task for bot_process in self.active_bots.values()],
                return_exceptions=True,
            )

        self.active_bots.clear()
        logger.info("All bots cleaned up")

    @asynccontextmanager
    async def managed_bot(self, room_url: str, token: str, bot_config: Dict[str, Any]):
        """Context manager for a managed bot lifecycle."""
        room_name = room_url.split("/")[-1]

        try:
            success = await self.start_bot(room_url, token, bot_config)
            if not success:
                raise RuntimeError(f"Failed to start bot for room {room_name}")

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
        asyncio.create_task(bot_service.cleanup())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


_setup_signal_handlers()
