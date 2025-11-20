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

from PIL import Image

from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
    LocalSmartTurnAnalyzerV3,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    LLMRunFrame,
    OutputImageRawFrame,
    SpriteFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

logger = logging.getLogger(__name__)


def load_bot_video_frames(
    bot_config: Dict[str, Any],
) -> tuple[Optional[OutputImageRawFrame], Optional[OutputImageRawFrame | SpriteFrame]]:
    """
    Load video frames for the bot based on configuration.

    Supports two modes:
    - "static": Load a single static image (e.g., robot01.png)
    - "animated": Load all frame_*.png files for sprite animation

    Args:
        bot_config: Bot configuration dictionary

    Returns:
        Tuple of (quiet_frame, talking_frame)
        - For static mode: Both frames are the same single image
        - For animated mode: quiet_frame is first frame, talking_frame is SpriteFrame with all frames
    """
    script_dir = os.path.dirname(__file__)
    hosting_dir = os.path.join(os.path.dirname(os.path.dirname(script_dir)), "hosting")
    sprites_dir = os.path.join(hosting_dir, "sprites")

    # Get video mode from config (default to "static")
    video_mode = bot_config.get("video_mode", "static")

    if video_mode == "static":
        # Load a single static image
        static_image = bot_config.get("static_image", "robot01.png")
        image_path = os.path.join(sprites_dir, static_image)

        if os.path.exists(image_path):
            with Image.open(image_path) as img:
                single_frame = OutputImageRawFrame(
                    image=img.tobytes(), size=img.size, format=img.mode
                )
            logger.info(f"Loaded static image from {image_path}")
            return (single_frame, single_frame)
        else:
            logger.warning(f"Static image not found: {image_path}")
            return (None, None)

    elif video_mode == "animated":
        # Load all frame_*.png files for animation
        frame_files = []
        if os.path.exists(sprites_dir):
            for filename in os.listdir(sprites_dir):
                if filename.startswith("frame_") and filename.endswith(".png"):
                    frame_files.append(filename)

            # Sort frames numerically
            frame_files.sort(
                key=lambda x: int(x.replace("frame_", "").replace(".png", ""))
            )

            if frame_files:
                sprites = []
                logger.info(
                    f"Loading {len(frame_files)} sprite frames from {sprites_dir}"
                )

                for frame_filename in frame_files:
                    full_path = os.path.join(sprites_dir, frame_filename)
                    with Image.open(full_path) as img:
                        sprites.append(
                            OutputImageRawFrame(
                                image=img.tobytes(), size=img.size, format=img.mode
                            )
                        )

                # Duplicate each frame to slow down the animation
                # This makes each frame display longer, creating a smoother, slower animation
                frames_per_sprite = bot_config.get(
                    "animation_frames_per_sprite", 3
                )  # Default: show each frame 3 times
                slowed_sprites = []
                for sprite in sprites:
                    for _ in range(frames_per_sprite):
                        slowed_sprites.append(sprite)

                logger.info(
                    f"Created animation with {len(slowed_sprites)} frames (slowed by {frames_per_sprite}x)"
                )

                # First frame for quiet state, animated SpriteFrame for talking
                quiet_frame = sprites[0] if sprites else None
                talking_frame = (
                    SpriteFrame(images=slowed_sprites) if slowed_sprites else None
                )

                return (quiet_frame, talking_frame)
            else:
                logger.warning(f"No frame files found in {sprites_dir}")
                return (None, None)
        else:
            logger.warning(f"Sprites directory not found: {sprites_dir}")
            return (None, None)

    else:
        logger.warning(f"Unknown video_mode: {video_mode}. Using static mode.")
        return (None, None)


class TalkingAnimation(FrameProcessor):
    """Manages the bot's visual animation states.

    Switches between static (listening) and animated (talking) states based on
    the bot's current speaking status.
    """

    def __init__(
        self,
        quiet_frame: Optional[OutputImageRawFrame] = None,
        talking_frame: Optional[OutputImageRawFrame | SpriteFrame] = None,
    ):
        super().__init__()
        self._is_talking = False
        self.quiet_frame = quiet_frame
        self.talking_frame = talking_frame

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and update animation state.

        Args:
            frame: The incoming frame to process
            direction: The direction of frame flow in the pipeline
        """
        await super().process_frame(frame, direction)

        # Switch to talking frame when bot starts speaking
        if isinstance(frame, BotStartedSpeakingFrame):
            if not self._is_talking and self.talking_frame is not None:
                await self.push_frame(self.talking_frame)
                self._is_talking = True
        # Return to static frame when bot stops speaking
        elif isinstance(frame, BotStoppedSpeakingFrame):
            if self.quiet_frame is not None:
                await self.push_frame(self.quiet_frame)
            self._is_talking = False

        await self.push_frame(frame, direction)


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
        try:

            system_message = bot_config.get(
                "system_message",
                "You are an AI interview host conducting a structured behavioral interview. "
                "Your output will be spoken aloud, so keep language natural and easy to say. "
                "Do not use special characters. Ask one question at a time. "
                "After asking a question, wait for the candidate's response before continuing. "
                "When the candidate finishes speaking, acknowledge their answer briefly, offer light positive reinforcement, and then move on. "
                "Keep your tone warm, steady, and professional. "
                "Follow these questions in order and do not add new ones unless the candidate asks for clarification.\n\n"
                "Questions:\n\n"
                "Tell me about a time you had to solve a difficult problem. What was the situation and what did you do.\n\n"
                "Describe a moment when you made a mistake at work. How did you handle it.\n\n"
                "Give an example of a time you had to work with a challenging teammate or stakeholder. What did you do to make it successful.\n\n"
                "Tell me about a goal you set that you had to work hard to achieve. How did you approach it.\n\n"
                "Describe a situation where you had to make a decision with incomplete information. How did you think through it.\n\n"
                "Guide the interview smoothly, keep the pacing natural, and help the candidate stay on track.",
            )

            bot_name = bot_config.get("name", "PailBot")

            transport = DailyTransport(
                room_url,
                token,
                bot_name,
                DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    video_out_enabled=True,  # Enable video output (static or animated based on config)
                    video_out_width=1280,
                    video_out_height=720,
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
            tts = OpenAITTSService(
                api_key=os.getenv("OPENAI_API_KEY"),
                voice="alloy",
                interruptions_allowed=True,
                interruption_strategies=[MinWordsInterruptionStrategy(min_words=3)],
            )

            messages = [
                {
                    "role": "system",
                    "content": system_message,
                },
            ]

            context = LLMContext(messages)
            context_aggregator = LLMContextAggregatorPair(context)

            # Load video frames based on bot configuration
            quiet_frame, talking_frame = load_bot_video_frames(bot_config)
            ta = TalkingAnimation(quiet_frame=quiet_frame, talking_frame=talking_frame)

            pipeline = Pipeline(
                [
                    transport.input(),
                    context_aggregator.user(),
                    llm,
                    tts,
                    ta,
                    transport.output(),
                    context_aggregator.assistant(),
                ]
            )

            task = PipelineTask(
                pipeline,
                params=PipelineParams(
                    enable_metrics=True,
                    enable_usage_metrics=True,
                ),
            )
            # Queue the initial frame if available
            if ta.quiet_frame is not None:
                await task.queue_frame(ta.quiet_frame)

            @transport.event_handler("on_participant_joined")
            async def on_participant_joined(transport, participant):
                """Log when any participant (including bot) joins."""
                participant_id = participant.get("id", "unknown")
                participant_name = participant.get("user_name", "unknown")
                is_local = participant.get("local", False)
                logger.info(
                    f"🔵 Participant joined - ID: {participant_id}, Name: {participant_name}, Local: {is_local}"
                )

            @transport.event_handler("on_first_participant_joined")
            async def on_first_participant_joined(transport, participant):
                participant_id = participant.get("id", "unknown")
                logger.info(f"🟢 FIRST participant joined: {participant_id}")
                await transport.capture_participant_transcription(participant["id"])
                logger.info(
                    f"✅ Started capturing transcription for participant: {participant_id}"
                )
                # Kick off the conversation with a greeting first
                # This tells the LLM to introduce itself before starting the interview
                messages.append(
                    {
                        "role": "system",
                        "content": "Please introduce yourself warmly to the user. Greet them and let them know you're here to conduct an interview. Wait for them to respond before starting with the interview questions.",
                    }
                )
                logger.info("📤 Queuing LLMRunFrame to start conversation...")
                await task.queue_frames([LLMRunFrame()])
                logger.info("✅ LLMRunFrame queued successfully")

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

            # **FOLLOW REFERENCE IMPLEMENTATION**: Use await runner.run(task) directly
            # This matches the reference implementation's blocking behavior exactly
            # The runner will block until the task completes (typically when participant leaves)
            await runner.run(task)

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
