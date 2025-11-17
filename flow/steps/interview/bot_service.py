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

try:
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
except ImportError as e:
    # Pipecat is required for bot functionality, but we allow the module to be imported
    # so that other code can check if bot_service is available
    raise ImportError(
        "Pipecat is required for bot functionality but is not installed. "
        "Install with: pip install pipecat-ai[daily,openai,local-smart-turn-v3]"
    ) from e

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

    async def start_bot(
        self, room_url: str, token: str, bot_config: Dict[str, Any]
    ) -> bool:
        """Start a bot instance for the given room."""
        try:
            room_name = room_url.split("/")[-1]

            if room_name in self.active_bots and self.active_bots[room_name].is_running:
                logger.warning(f"Bot already running for room: {room_name}")
                return True

            # Validate configuration
            self._validate_bot_config(bot_config)

            # Create bot task
            bot_task = asyncio.create_task(self._run_bot(room_url, token, bot_config))

            # Track the bot
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

    def _validate_bot_config(self, bot_config: Dict[str, Any]) -> None:
        """Validate bot configuration parameters."""
        if not isinstance(bot_config, dict):
            raise ValueError("Bot config must be a dictionary")

        # Validate system message
        system_message = bot_config.get("system_message", "")
        if len(system_message) > 2000:
            raise ValueError("System message too long (max 2000 characters)")

        # Validate bot name
        bot_name = bot_config.get("name", "PailBot")
        if not isinstance(bot_name, str) or len(bot_name) > 50:
            raise ValueError("Bot name must be a string (max 50 characters)")

    async def _run_bot(
        self, room_url: str, token: str, bot_config: Dict[str, Any]
    ) -> None:
        """Run the Pipecat bot directly without subprocess."""
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

            @transport.event_handler("on_first_participant_joined")
            async def on_first_participant_joined(transport, participant):
                logger.info(f"First participant joined: {participant['id']}")
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
            await runner.run(task)
            logger.info("Bot pipeline runner finished")

        except Exception as e:
            logger.error(f"Bot process error: {e}", exc_info=True)
            raise

    def _cleanup_bot(self, room_name: str) -> None:
        """Clean up a bot that has finished."""
        if room_name in self.active_bots:
            bot_process = self.active_bots[room_name]
            logger.info(
                f"Cleaning up bot for room {room_name} (ran for {bot_process.runtime_seconds:.1f}s)"
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
                result[room_name] = status
        return result

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
