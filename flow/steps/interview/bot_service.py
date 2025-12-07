# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Pipecat Bot Service - AI bot that joins Daily meetings."""

import asyncio
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

import requests
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
    TranscriptionMessage,
    TranscriptionUpdateFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

logger = logging.getLogger(__name__)

# Note: "Event loop is closed" RuntimeErrors may appear in logs when the bot finishes.
# These come from Daily.co transport's WebSocket callbacks trying to post to a closed loop.
# They are harmless and expected during cleanup - the bot still functions correctly.


class TranscriptHandler:
    """
    Handles real-time transcript processing and saves to database.

    Attributes:
        messages: List of all processed transcript messages
        room_name: Room name for saving to database
        transcript_text: Accumulated transcript text
    """

    def __init__(self, room_name: str):
        """
        Initialize handler with database storage.

        Args:
            room_name: Room name for saving transcript to database
        """
        self.messages: list[TranscriptionMessage] = []
        self.room_name: str = room_name
        self.transcript_text: str = ""
        logger.info(f"TranscriptHandler initialized for room: {room_name}")

    def _format_transcript_line(
        self, role: str, content: str, timestamp: Optional[str] = None
    ) -> str:
        """
        Format a transcript message as a line of text.

        Args:
            role: Role of speaker (user/assistant)
            content: The transcript text
            timestamp: Optional timestamp string

        Returns:
            Formatted line string
        """
        timestamp_str = f"[{timestamp}] " if timestamp else ""
        return f"{timestamp_str}{role}: {content}"

    def add_daily_transcript(
        self, participant_id: str, text: str, is_final: bool = False
    ):
        """
        Legacy method for Daily.co transcription (not used with Deepgram STT).

        Args:
            participant_id: Participant ID from Daily.co
            text: The transcribed text
            is_final: Whether this is a final transcript (vs interim)
        """
        # This method is deprecated - transcripts come from TranscriptProcessor via on_transcript_update
        logger.debug(
            "add_daily_transcript called but not used (using Deepgram STT instead)"
        )

    async def _save_to_database(self):
        """
        Save accumulated transcript to database.
        """
        try:
            from flow.db import get_session_data, save_session_data

            # Get existing session data
            session_data = get_session_data(self.room_name) or {}

            # Update transcript text
            session_data["transcript_text"] = self.transcript_text

            # Save back to database
            save_session_data(self.room_name, session_data)
            logger.debug(f"✅ Transcript saved to database for room: {self.room_name}")
        except Exception as e:
            logger.error(f"Error saving transcript to database: {e}", exc_info=True)

    async def on_transcript_update(
        self, processor: TranscriptProcessor, frame: TranscriptionUpdateFrame
    ):
        """
        Handle new transcript messages from the TranscriptProcessor.

        Args:
            processor: The TranscriptProcessor that emitted the update
            frame: TranscriptionUpdateFrame containing new messages
        """
        logger.debug(
            f"Received transcript update with {len(frame.messages)} new messages"
        )

        for msg in frame.messages:
            # Capture both user and assistant messages from TranscriptProcessor
            # User messages come from Deepgram STT, assistant messages from TTS
            self.messages.append(msg)

            # Format and add to transcript text
            role_label = "user" if msg.role == "user" else "assistant"
            line = self._format_transcript_line(role_label, msg.content, msg.timestamp)
            self.transcript_text += line + "\n"

            # Log the message
            logger.info(f"Transcript ({role_label.capitalize()}): {line}")

            # Save to database (updates session data with latest transcript)
            await self._save_to_database()


def load_bot_video_frames(
    bot_config: Dict[str, Any],
) -> tuple[
    Optional[OutputImageRawFrame],
    Optional[OutputImageRawFrame | SpriteFrame | list[OutputImageRawFrame]],
]:
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
    # Try both lowercase and capitalized directory names (case-insensitive)
    sprites_dir_lower = os.path.join(hosting_dir, "sprites")
    sprites_dir_upper = os.path.join(hosting_dir, "Sprites")
    if os.path.exists(sprites_dir_upper):
        sprites_dir = sprites_dir_upper
    else:
        sprites_dir = sprites_dir_lower

    # Get video mode from config (default to "animated")
    video_mode = bot_config.get("video_mode", "animated")

    if video_mode == "static":
        # Load a single static image
        static_image = bot_config.get("static_image", "robot01.png")
        image_path = os.path.join(sprites_dir, static_image)

        if os.path.exists(image_path):
            with Image.open(image_path) as img:
                # Convert RGBA to RGB to remove alpha channel and prevent compositing
                if img.mode == "RGBA":
                    # Create a white background and paste the RGBA image on it
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                    img = rgb_img
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                single_frame = OutputImageRawFrame(
                    image=img.tobytes(), size=img.size, format=img.mode
                )
            logger.info(f"Loaded static image from {image_path}")
            return (single_frame, single_frame)
        else:
            logger.warning(f"Static image not found: {image_path}")
            return (None, None)

    elif video_mode == "animated":
        # Load all frame_*.png files for animation (case-insensitive)
        frame_files = []
        if os.path.exists(sprites_dir):
            for filename in os.listdir(sprites_dir):
                # Case-insensitive matching for frame files
                if filename.lower().startswith("frame_") and filename.lower().endswith(
                    ".png"
                ):
                    frame_files.append(filename)

            # Sort frames numerically (case-insensitive)
            frame_files.sort(
                key=lambda x: int(x.lower().replace("frame_", "").replace(".png", ""))
            )

            if frame_files:
                sprites = []
                logger.info(
                    f"Loading {len(frame_files)} sprite frames from {sprites_dir}"
                )

                for frame_filename in frame_files:
                    full_path = os.path.join(sprites_dir, frame_filename)
                    with Image.open(full_path) as img:
                        # Convert RGBA to RGB to remove alpha channel and prevent compositing
                        if img.mode == "RGBA":
                            # Create a white background and paste the RGBA image on it
                            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                            rgb_img.paste(
                                img, mask=img.split()[3]
                            )  # Use alpha channel as mask
                            img = rgb_img
                        elif img.mode != "RGB":
                            img = img.convert("RGB")
                        sprites.append(
                            OutputImageRawFrame(
                                image=img.tobytes(), size=img.size, format=img.mode
                            )
                        )

                # Create a smooth animation by adding reversed frames (like reference implementation)
                # This makes the animation go forward then backward, creating a smooth loop
                flipped = sprites[::-1]
                sprites.extend(flipped)
                logger.info(
                    f"Added reversed frames: {len(sprites)} total frames (forward + backward)"
                )

                # Duplicate each frame to slow down the animation (like reference implementation)
                # This makes each frame display longer, creating a smoother, slower animation
                frames_per_sprite = bot_config.get(
                    "animation_frames_per_sprite", 1
                )  # Default: show each frame 3 times
                slowed_sprites = []
                for sprite in sprites:
                    for _ in range(frames_per_sprite):
                        slowed_sprites.append(sprite)

                logger.info(
                    f"Created animation with {len(slowed_sprites)} frames (slowed by {frames_per_sprite}x)"
                )

                # First frame for quiet state, animated SpriteFrame for talking
                # SpriteFrame handles animation internally - we just push it once
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
        # SpriteFrame handles animation internally - we just push it once
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
        # Simple Explanation: bot_id_map tracks which bot_id is associated with each room_name
        # This allows us to update bot session records when the bot finishes
        self.bot_id_map: Dict[str, str] = {}
        # Simple Explanation: bot_config_map stores bot configuration for each room
        # This includes whether to process insights after the bot finishes
        self.bot_config_map: Dict[str, Dict[str, Any]] = {}

        # Fly.io configuration - read from environment variables
        self.fly_api_host = os.getenv("FLY_API_HOST", "https://api.machines.dev/v1")
        self.fly_app_name = os.getenv("FLY_APP_NAME", "")
        self.fly_api_key = os.getenv("FLY_API_KEY", "")
        self.use_fly_machines = bool(self.fly_api_key and self.fly_app_name)

        if self.use_fly_machines:
            logger.info(
                f"✅ Fly.io machine spawning enabled (app: {self.fly_app_name})"
            )
        else:
            logger.info(
                "ℹ️ Fly.io machine spawning disabled - using direct execution. "
                "Set FLY_API_KEY and FLY_APP_NAME to enable."
            )

    def _spawn_fly_machine(
        self, room_url: str, token: str, bot_config: Dict[str, Any]
    ) -> str:
        """
        Spawn a new Fly.io machine to run the bot.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary

        Returns:
            Machine ID of the spawned machine

        Raises:
            Exception: If machine spawning fails
        """
        if not self.use_fly_machines:
            raise RuntimeError(
                "Fly.io machine spawning is not enabled. "
                "Set FLY_API_KEY and FLY_APP_NAME environment variables."
            )

        headers = {
            "Authorization": f"Bearer {self.fly_api_key}",
            "Content-Type": "application/json",
        }

        # Get the Docker image from the current app
        res = requests.get(
            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines",
            headers=headers,
        )
        if res.status_code != 200:
            raise Exception(f"Unable to get machine info from Fly: {res.text}")

        machines = res.json()
        if not machines:
            raise Exception("No machines found in Fly app to get image from")

        image = machines[0]["config"]["image"]
        logger.info(f"Using Docker image: {image}")

        # Prepare bot config as JSON for the command
        bot_config_json = json.dumps(bot_config)

        # Machine configuration
        cmd = [
            "python3",
            "flow/steps/interview/bot.py",
            "-u",
            room_url,
            "-t",
            token,
            "--bot-config",
            bot_config_json,
        ]

        worker_props = {
            "config": {
                "image": image,
                "auto_destroy": True,  # Machine destroys itself when bot exits
                "init": {"cmd": cmd},
                "restart": {"policy": "no"},  # Don't restart - let it exit cleanly
                "guest": {
                    "cpu_kind": "shared",
                    "cpus": 1,
                    "memory_mb": 1024,  # 1GB RAM - enough for VAD and bot processing
                },
                "env": {
                    # Pass through required environment variables
                    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", ""),
                    "DAILY_API_KEY": os.getenv("DAILY_API_KEY", ""),
                },
            },
        }

        # Spawn a new machine instance
        logger.info(
            f"Spawning Fly.io machine for bot (room: {room_url.split('/')[-1]})"
        )
        res = requests.post(
            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines",
            headers=headers,
            json=worker_props,
        )

        if res.status_code != 200:
            raise Exception(f"Problem starting a bot worker: {res.text}")

        # Get the machine ID from the response
        vm_id = res.json()["id"]
        logger.info(f"✅ Machine spawned: {vm_id}")

        # Wait for the machine to enter the started state
        res = requests.get(
            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}/wait?state=started",
            headers=headers,
        )

        if res.status_code != 200:
            raise Exception(f"Bot was unable to enter started state: {res.text}")

        logger.info(f"✅ Machine {vm_id} is started and ready")
        return vm_id

    async def start_bot(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        room_name: Optional[str] = None,
        use_fly_machines: Optional[bool] = None,
        bot_id: Optional[str] = None,
    ) -> bool:
        """
        Start a bot instance for the given room.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            room_name: Optional room name (extracted from URL if not provided)
            use_fly_machines: Whether to use Fly.io machines (None = auto-detect from config)
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
                    return True

                if should_use_fly:
                    # Spawn a Fly.io machine for the bot
                    try:
                        vm_id = self._spawn_fly_machine(room_url, token, bot_config)
                        logger.info(
                            f"✅ Bot spawned on Fly.io machine {vm_id} for room {room_name}"
                        )
                        # For Fly.io machines, we don't track them in active_bots
                        # because they run independently and auto-destroy when done
                        return True
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to spawn Fly.io machine: {e}", exc_info=True
                        )
                        # Fall back to direct execution if Fly.io fails
                        logger.info("Falling back to direct execution...")
                        should_use_fly = False

                if not should_use_fly:
                    # Direct execution: run bot in current process
                    # Simple Explanation: Store bot_id and config for this room so we can
                    # process results when the bot finishes
                    if bot_id:
                        self.bot_id_map[room_name] = bot_id
                    self.bot_config_map[room_name] = bot_config

                    bot_task = asyncio.create_task(
                        self._run_bot(room_url, token, bot_config, room_name)
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
                            logger.error(
                                f"❌ Bot task failed immediately: {e}", exc_info=True
                            )
                            return False
                    else:
                        logger.info("✅ Bot task is running (not done yet)")

                return True

        except Exception as e:
            logger.error(f"Failed to start bot: {e}", exc_info=True)
            return False

    async def _run_bot(
        self, room_url: str, token: str, bot_config: Dict[str, Any], room_name: str
    ) -> None:
        """
        Run the Pipecat bot directly without subprocess.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            room_name: Room name for saving transcript to database
        """
        try:

            # Get bot prompt from config - this defines what the bot should do/say
            # If not provided, use a generic default
            bot_prompt = bot_config.get(
                "bot_prompt",
                bot_config.get(
                    "system_message",  # Fallback to old field name for backwards compatibility
                    "You are a helpful AI assistant. "
                    "Your output will be spoken aloud, so keep language natural and easy to say. "
                    "Do not use special characters. "
                    "Have a natural conversation with the participant.",
                ),
            )

            # Add voice-specific instructions to any prompt
            system_message = f"""{bot_prompt}

IMPORTANT: Your output will be spoken aloud, so:
- Keep language natural and conversational
- Do not use special characters, markdown, or formatting
- Speak in complete sentences
- Wait for the participant to finish speaking before responding
- Keep responses concise and clear"""

            bot_name = bot_config.get("name", "PailBot")

            transport = DailyTransport(
                room_url,
                token,
                bot_name,
                DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    video_out_enabled=True,  # Enable video output (static or animated based on config)
                    video_out_width=1280,  # Match reference implementation
                    video_out_height=720,  # Match reference implementation
                    transcription_enabled=False,  # We use Deepgram STT instead of Daily.co transcription
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

            # Use Deepgram for Speech-to-Text (STT) to transcribe user speech
            stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

            messages = [
                {
                    "role": "system",
                    "content": system_message,
                },
            ]

            context = LLMContext(messages)
            context_aggregator = LLMContextAggregatorPair(context)

            # Create transcript processor and handler
            transcript = TranscriptProcessor()

            # Create transcript handler that saves to database
            transcript_handler = TranscriptHandler(room_name=room_name)
            logger.info(
                f"📝 Transcript will be saved to database for room: {room_name}\n"
                "   - User speech: Deepgram STT (from pipeline)\n"
                "   - Bot speech: TranscriptProcessor (from TTS input)"
            )

            # Load video frames based on bot configuration
            quiet_frame, talking_frame = load_bot_video_frames(bot_config)
            ta = TalkingAnimation(quiet_frame=quiet_frame, talking_frame=talking_frame)

            # Build pipeline with Deepgram STT and TranscriptProcessor
            pipeline_components = [
                transport.input(),  # Transport user input
                stt,  # Deepgram STT - converts user speech to text
                transcript.user(),  # User transcripts (from STT)
                context_aggregator.user(),  # User responses
                llm,  # LLM
                tts,  # TTS
                ta,  # Talking animation (for video output)
                transport.output(),  # Transport bot output
                transcript.assistant(),  # Assistant transcripts (after transport.output())
                context_aggregator.assistant(),  # Assistant spoken responses
            ]

            pipeline = Pipeline(pipeline_components)

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

            # Register event handler for transcript updates from TranscriptProcessor
            @transcript.event_handler("on_transcript_update")
            async def on_transcript_update(processor, frame):
                await transcript_handler.on_transcript_update(processor, frame)

            @transport.event_handler("on_first_participant_joined")
            async def on_first_participant_joined(transport, participant):
                participant_id = participant.get("id", "unknown")
                logger.info(f"🟢 FIRST participant joined: {participant_id}")
                # Note: We no longer use capture_participant_transcription here
                # because TranscriptProcessor handles transcription automatically
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

            @transport.event_handler("participant-counts-updated")
            async def on_participant_counts_updated(transport, event):
                """
                Handle participant-counts-updated event from Daily.co.

                Simple Explanation: This event fires when participants join or leave.
                We log the current participant counts for debugging and monitoring.
                """
                try:
                    # Get participant counts from transport
                    # Simple Explanation: participantCounts() returns information about
                    # how many participants are currently in the room (present and hidden).
                    counts = transport.participantCounts()
                    if counts:
                        present = counts.get("present", 0)
                        hidden = counts.get("hidden", 0)
                        logger.info(
                            f"👥 Participant counts updated - Present: {present}, Hidden: {hidden}"
                        )
                    else:
                        logger.debug("Participant counts not available")
                except Exception as e:
                    logger.debug(f"Error getting participant counts: {e}")

            @transport.event_handler("on_participant_left")
            async def on_participant_left(transport, participant, reason):
                """
                Handle participant left event.

                Simple Explanation: When a participant (including the bot) leaves,
                we check if there's a workflow waiting to resume. If so, we resume
                it to continue processing the transcript. Otherwise, we process
                results directly (legacy behavior).
                """
                participant_id = participant.get("id", "unknown")
                logger.info(f"Participant left: {participant_id}, reason: {reason}")

                # Check if there's a workflow waiting to resume
                # Simple Explanation: If a workflow was started via the bot_call
                # workflow, it will have a workflow_thread_id in session_data. We
                # resume the workflow instead of processing results directly.
                from flow.db import get_session_data

                session_data = get_session_data(room_name) or {}
                workflow_thread_id = session_data.get("workflow_thread_id")

                if workflow_thread_id:
                    # Resume the workflow
                    # Simple Explanation: The workflow paused after starting the bot.
                    # Now that the bot has finished, we resume it to continue to the
                    # process_transcript step.
                    logger.info(
                        f"🔄 Resuming workflow with thread_id: {workflow_thread_id}"
                    )
                    try:
                        from flow.workflows.bot_call import BotCallWorkflow

                        workflow = BotCallWorkflow()
                        config = {"configurable": {"thread_id": workflow_thread_id}}

                        # Simple Explanation: LangGraph automatically resumes from the latest
                        # checkpoint when you call ainvoke with a config containing a thread_id.
                        # We just need to pass an empty state dict - LangGraph will load the
                        # state from the checkpoint automatically.
                        # Resume the workflow - it will continue to process_transcript node
                        await workflow.graph.ainvoke({}, config=config)
                        logger.info("✅ Workflow resumed successfully")
                    except Exception as e:
                        logger.error(f"❌ Error resuming workflow: {e}", exc_info=True)
                        # Fallback to full transcript processing if workflow resume fails
                        # Simple Explanation: If workflow resume fails, we use ProcessTranscriptStep
                        # which includes the full pipeline: Q&A parsing, insights, email, webhook
                        logger.info("   Falling back to full transcript processing...")
                        await self._process_bot_results_full_pipeline(
                            room_name, transcript_handler
                        )
                else:
                    # No workflow - use full transcript processing pipeline
                    # Simple Explanation: Even without a workflow, we should run the full
                    # ProcessTranscriptStep pipeline to ensure emails and webhooks are sent
                    logger.info(
                        "   No workflow_thread_id - processing with full pipeline..."
                    )
                    await self._process_bot_results_full_pipeline(
                        room_name, transcript_handler
                    )

                # Cancel the task to clean up
                await task.cancel()

            # PipelineRunner tries to set up signal handlers in __init__, but this only works in the main thread.
            # Since we're running in a background task, we need to create the runner in a way that
            # skips signal handler setup. We'll monkey-patch the _setup_sigint method to be a no-op.
            import pipecat.pipeline.runner as runner_module

            original_setup_sigint = runner_module.PipelineRunner._setup_sigint

            # Temporarily disable signal handler setup
            def noop_setup_sigint(self):
                """No-op signal handler setup for background threads."""
                pass

            # Replace the method temporarily
            runner_module.PipelineRunner._setup_sigint = noop_setup_sigint
            try:
                runner = PipelineRunner()
                logger.info(
                    "✅ PipelineRunner created (signal handlers disabled for background thread)"
                )
            finally:
                # Restore original method
                runner_module.PipelineRunner._setup_sigint = original_setup_sigint

            logger.info("Starting bot pipeline runner...")
            logger.info(f"   Transport created: {transport}")
            logger.info(f"   Task created: {task}")
            logger.info(f"   Runner created: {runner}")

            # **FOLLOW REFERENCE IMPLEMENTATION**: Use await runner.run(task) directly
            # This matches the reference implementation's blocking behavior exactly
            # The runner will block until the task completes (typically when participant leaves)
            try:
                logger.info("🚀 Calling runner.run(task)...")
                await runner.run(task)
                logger.info("✅ runner.run(task) completed")

                # Simple Explanation: After the bot finishes, the on_participant_left handler
                # will either resume the workflow (if workflow_thread_id exists) or process
                # results directly (legacy behavior). We don't need to call _process_bot_results
                # here anymore - it's handled in the event handler.
                # Note: The workflow resume happens in on_participant_left, so we don't need
                # to do anything here. If there's no workflow, on_participant_left will
                # call _process_bot_results directly.
            finally:
                # When the bot task finishes, the Daily.co transport might still have pending callbacks
                # that try to post to the event loop. We need to properly clean up the transport
                # to prevent "Event loop is closed" errors.
                try:
                    # Clean up the transport to prevent callbacks after task completion
                    if hasattr(transport, "cleanup") and callable(transport.cleanup):
                        await transport.cleanup()
                    elif hasattr(transport, "close") and callable(transport.close):
                        await transport.close()
                    logger.info("✅ Transport cleaned up successfully")
                except (RuntimeError, asyncio.CancelledError) as cleanup_error:
                    # Ignore cleanup errors - transport might already be closed
                    # These are expected when the event loop is closing
                    # "Event loop is closed" errors are common during cleanup
                    error_msg = str(cleanup_error)
                    if (
                        "Event loop is closed" in error_msg
                        or "loop is closed" in error_msg.lower()
                    ):
                        logger.debug(
                            f"Transport cleanup warning (expected during shutdown): {cleanup_error}"
                        )
                    else:
                        logger.warning(f"Transport cleanup warning: {cleanup_error}")
                except Exception as cleanup_error:
                    # Other cleanup errors - log but don't fail
                    logger.debug(f"Transport cleanup warning: {cleanup_error}")

        except asyncio.CancelledError:
            # Task was cancelled - this is expected when participant leaves
            logger.info("🛑 Bot task was cancelled (participant left)")
            # Ensure transport is cleaned up even on cancellation
            try:
                if (
                    "transport" in locals()
                    and hasattr(transport, "cleanup")
                    and callable(transport.cleanup)
                ):
                    await transport.cleanup()
            except (RuntimeError, asyncio.CancelledError) as e:
                # Ignore "Event loop is closed" errors during cancellation - these are expected
                if "Event loop is closed" not in str(e):
                    logger.debug(f"Transport cleanup during cancellation: {e}")
            except Exception:
                pass  # Ignore other cleanup errors during cancellation
            raise
        except Exception as e:
            logger.error(f"❌ Bot process error: {e}", exc_info=True)
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error message: {str(e)}")
            # Ensure transport is cleaned up even on error
            try:
                if (
                    "transport" in locals()
                    and hasattr(transport, "cleanup")
                    and callable(transport.cleanup)
                ):
                    await transport.cleanup()
            except (RuntimeError, asyncio.CancelledError) as cleanup_e:
                # Ignore "Event loop is closed" errors during error handling - these are expected
                if "Event loop is closed" not in str(cleanup_e):
                    logger.debug(f"Transport cleanup during error: {cleanup_e}")
            except Exception:
                pass  # Ignore other cleanup errors during error handling
            raise

    async def _process_bot_results_full_pipeline(
        self, room_name: str, transcript_handler: TranscriptHandler
    ) -> None:
        """
        Process transcript using the full ProcessTranscriptStep pipeline.

        Simple Explanation: After the bot finishes transcribing, we run the complete
        ProcessTranscriptStep which handles:
        1. Parsing transcript to extract Q&A pairs
        2. Extracting insights using AI analysis (if enabled)
        3. Generating candidate summary
        4. Sending email (if configured)
        5. Triggering webhook (if configured)
        6. Storing results in the database

        Args:
            room_name: Room name for this bot session
            transcript_handler: The transcript handler that collected the transcript
        """
        try:
            logger.info(
                f"🔄 Processing results with full pipeline for bot in room: {room_name}"
            )

            # Get transcript text from handler
            transcript_text = transcript_handler.transcript_text

            if not transcript_text:
                logger.warning(f"⚠️ No transcript text found for room {room_name}")
                return

            # Use ProcessTranscriptStep for the full pipeline
            # Simple Explanation: ProcessTranscriptStep.execute() handles the complete
            # processing pipeline including Q&A parsing, insights, summary, email, and webhook
            from flow.steps.interview.process_transcript import ProcessTranscriptStep

            # Create state for ProcessTranscriptStep
            # Simple Explanation: ProcessTranscriptStep expects room_name and will
            # automatically retrieve transcript_text from the database if not provided
            state = {
                "room_name": room_name,
                # ProcessTranscriptStep will check database for transcript_text automatically
                # The bot saves it there as it transcribes
            }

            # Execute the full pipeline
            logger.info(
                "   🔄 Calling ProcessTranscriptStep.execute() for full pipeline..."
            )
            process_step = ProcessTranscriptStep()
            result = await process_step.execute(state)

            # Check for errors
            if result.get("error"):
                logger.error(f"❌ ProcessTranscriptStep error: {result.get('error')}")
                return

            logger.info("   ✅ Full transcript processing pipeline complete")
            logger.info(f"      - Email sent: {result.get('email_sent', False)}")
            logger.info(f"      - Webhook sent: {result.get('webhook_sent', False)}")

        except Exception as e:
            logger.error(
                f"❌ Error processing bot results with full pipeline for room {room_name}: {e}",
                exc_info=True,
            )
            # Don't raise - we don't want to fail the bot cleanup if processing fails

    async def _process_bot_results(
        self, room_name: str, transcript_handler: TranscriptHandler
    ) -> None:
        """
        Process transcript and extract insights after bot finishes (legacy method).

        Simple Explanation: After the bot finishes transcribing, we automatically:
        1. Process the transcript to extract Q&A pairs
        2. Extract insights using AI analysis (if enabled)
        3. Store results in the database so they can be retrieved via the status endpoint

        Note: This method does NOT send emails or webhooks. Use _process_bot_results_full_pipeline
        for the complete pipeline including email and webhook.

        Args:
            room_name: Room name for this bot session
            transcript_handler: The transcript handler that collected the transcript
        """
        try:
            logger.info(f"🔄 Processing results for bot in room: {room_name}")

            # Get bot config to check if insights processing is enabled
            bot_config = self.bot_config_map.get(room_name, {})
            process_insights = bot_config.get("process_insights", True)

            # Get transcript text from handler
            transcript_text = transcript_handler.transcript_text

            if not transcript_text:
                logger.warning(f"⚠️ No transcript text found for room {room_name}")
                return

            # Create state dictionary for processing steps
            # Simple Explanation: The ProcessTranscriptStep and ExtractInsightsStep
            # expect a state dictionary with transcript and other data. We create
            # this state object and pass it through the processing steps.
            from flow.steps.interview.process_transcript import (
                parse_transcript_to_qa_pairs,
            )
            from flow.steps.interview.extract_insights import ExtractInsightsStep

            state = {
                "room_name": room_name,
                "interview_transcript": transcript_text,
            }

            # Parse transcript to extract Q&A pairs
            logger.info("📝 Parsing transcript to extract Q&A pairs...")
            qa_pairs = parse_transcript_to_qa_pairs(transcript_text)
            state["qa_pairs"] = qa_pairs
            logger.info(f"✅ Extracted {len(qa_pairs)} Q&A pairs")

            # Extract insights if enabled
            if process_insights:
                logger.info("🧠 Extracting insights...")
                extract_insights_step = ExtractInsightsStep()
                state = await extract_insights_step.execute(state)

                if state.get("error"):
                    logger.error(f"❌ Error extracting insights: {state.get('error')}")
                else:
                    logger.info("✅ Insights extracted successfully")

            # Save results to database
            # Simple Explanation: We save the transcript, Q&A pairs, and insights
            # to the database so they can be retrieved via the status endpoint.
            from flow.db import (
                get_session_data,
                save_session_data,
                get_bot_session_by_room_name,
                save_bot_session,
            )

            # Save to rooms table (for backwards compatibility)
            session_data = get_session_data(room_name) or {}
            session_data["transcript_text"] = transcript_text
            session_data["qa_pairs"] = qa_pairs
            if process_insights and state.get("insights"):
                session_data["insights"] = state["insights"]

            save_session_data(room_name, session_data)
            logger.info(
                f"✅ Saved processing results to rooms table for room: {room_name}"
            )

            # Also save to bot_sessions table if we have a bot_id
            # Simple Explanation: We also save results to the bot_sessions table
            # so the status endpoint can retrieve them directly by bot_id
            if hasattr(self, "bot_id_map") and room_name in self.bot_id_map:
                bot_id = self.bot_id_map[room_name]
                bot_session = get_bot_session_by_room_name(room_name)

                if bot_session and bot_session.get("bot_id") == bot_id:
                    # Update bot session with results
                    bot_session["status"] = "completed"
                    bot_session["completed_at"] = datetime.utcnow().isoformat() + "Z"
                    bot_session["transcript_text"] = transcript_text
                    bot_session["qa_pairs"] = qa_pairs
                    if process_insights and state.get("insights"):
                        bot_session["insights"] = state["insights"]

                    save_bot_session(bot_id, bot_session)
                    logger.info(
                        f"✅ Saved processing results to bot_sessions table for bot_id: {bot_id}"
                    )

        except Exception as e:
            logger.error(
                f"❌ Error processing bot results for room {room_name}: {e}",
                exc_info=True,
            )
            # Don't raise - we don't want to fail the bot cleanup if processing fails

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
