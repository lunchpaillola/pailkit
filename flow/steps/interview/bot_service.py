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
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from pipecat.transports.daily.transport import DailyTransport

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
        bot_name: Bot's name (for assistant messages)
        speaker_tracker: Reference to SpeakerTrackingProcessor
        transport: DailyTransport instance
        participants_map: Dict mapping session_id -> participant info
        bot_session_id: Bot's own session_id
    """

    def __init__(
        self,
        room_name: str,
        bot_name: Optional[str] = None,
        speaker_tracker: Optional["SpeakerTrackingProcessor"] = None,
        transport: Optional["DailyTransport"] = None,
        workflow_thread_id: Optional[str] = None,
    ):
        """
        Initialize handler with database storage.

        Args:
            room_name: Room name for saving transcript to database
            bot_name: Bot's name (for assistant messages)
            speaker_tracker: Reference to SpeakerTrackingProcessor
            transport: DailyTransport instance to access participants()
            workflow_thread_id: Optional workflow_thread_id to save transcript to workflow_threads
        """
        self.messages: list[TranscriptionMessage] = []
        self.room_name: str = room_name
        self.transcript_text: str = ""
        self.bot_name: str = bot_name or "Assistant"
        self.speaker_tracker: Optional["SpeakerTrackingProcessor"] = speaker_tracker
        self.transport: Optional["DailyTransport"] = transport
        self.participants_map: Dict[str, Dict[str, Any]] = {}
        self.participant_join_order: list[str] = (
            []
        )  # Track participant join order for mapping
        self.bot_session_id: Optional[str] = None
        self.workflow_thread_id: Optional[str] = workflow_thread_id
        logger.info(
            f"TranscriptHandler initialized for room: {room_name}, bot_name: {self.bot_name}, workflow_thread_id: {workflow_thread_id}"
        )

    def _normalize_timestamp(
        self, timestamp: Optional[Union[str, float, int]]
    ) -> Optional[str]:
        """
        Convert timestamp to ISO format string.

        Args:
            timestamp: Timestamp as string, float (Unix timestamp), int, or None

        Returns:
            ISO format timestamp string, or None if timestamp is None
        """
        if timestamp is None:
            return None
        if isinstance(timestamp, str):
            return timestamp  # Assume already formatted
        if isinstance(timestamp, (int, float)):
            # Convert Unix timestamp to ISO format
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        return None

    def _format_transcript_line(
        self,
        speaker_name: str,
        content: str,
        timestamp: Optional[Union[str, float, int]] = None,
    ) -> str:
        """
        Format a transcript message as a line of text.

        Args:
            speaker_name: Name of the speaker (bot name or participant name)
            content: The transcript text
            timestamp: Optional timestamp (string, float, or int) - will be normalized to ISO format

        Returns:
            Formatted line string
        """
        normalized_timestamp = self._normalize_timestamp(timestamp)
        timestamp_str = f"[{normalized_timestamp}] " if normalized_timestamp else ""
        return f"{timestamp_str}{speaker_name}: {content}"

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
            # Save to workflow_threads table if we have a workflow_thread_id
            if self.workflow_thread_id:
                from flow.db import get_workflow_thread_data, save_workflow_thread_data

                workflow_thread_data = (
                    get_workflow_thread_data(self.workflow_thread_id) or {}
                )
                workflow_thread_data["workflow_thread_id"] = self.workflow_thread_id
                workflow_thread_data["transcript_text"] = self.transcript_text

                save_workflow_thread_data(self.workflow_thread_id, workflow_thread_data)
                logger.debug(
                    f"✅ Transcript saved to workflow_threads: workflow_thread_id={self.workflow_thread_id}"
                )
            else:
                # Fallback: try to find workflow_thread_id by room_name
                from flow.db import get_workflow_threads_by_room_name

                threads = get_workflow_threads_by_room_name(self.room_name)
                # Get the most recent paused workflow thread
                for thread in threads:
                    if thread.get("workflow_paused"):
                        workflow_thread_id = thread.get("workflow_thread_id")
                        if workflow_thread_id:
                            from flow.db import (
                                get_workflow_thread_data,
                                save_workflow_thread_data,
                            )

                            workflow_thread_data = (
                                get_workflow_thread_data(workflow_thread_id) or {}
                            )
                            workflow_thread_data["workflow_thread_id"] = (
                                workflow_thread_id
                            )
                            workflow_thread_data["transcript_text"] = (
                                self.transcript_text
                            )

                            save_workflow_thread_data(
                                workflow_thread_id, workflow_thread_data
                            )
                            logger.debug(
                                f"✅ Transcript saved to workflow_threads (found by room_name): workflow_thread_id={workflow_thread_id}"
                            )
                            # Cache the workflow_thread_id for future saves
                            self.workflow_thread_id = workflow_thread_id
                            break
                else:
                    logger.warning(
                        f"⚠️ No workflow_thread_id found for room: {self.room_name} - transcript not saved"
                    )
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
        logger.info(f"📝 Received transcript update: {len(frame.messages)} messages")

        for msg in frame.messages:
            # Capture both user and assistant messages from TranscriptProcessor
            # User messages come from Deepgram STT, assistant messages from TTS
            self.messages.append(msg)

            # Get user_id from message (Daily.co participant ID)
            msg_user_id = getattr(msg, "user_id", None)

            # Determine speaker name based on role
            if msg.role == "assistant":
                # Assistant messages = bot speaking - always use bot name
                speaker_name = self.bot_name
            else:
                # User messages = human participants - lookup by user_id
                speaker_name = "User"  # Default fallback

                participant_info = None

                # Try to find participant by user_id
                if msg_user_id:
                    # Try direct lookup by user_id as session_id
                    participant_info = self.participants_map.get(msg_user_id)
                    if not participant_info:
                        # Search for participant where user_id or id matches
                        for sid, p_info in self.participants_map.items():
                            p_user_id = p_info.get("user_id")
                            p_id = p_info.get("id")
                            if p_user_id == msg_user_id or p_id == msg_user_id:
                                participant_info = p_info
                                break

                # If found, use participant name
                if participant_info:
                    speaker_name = (
                        participant_info.get("name")
                        or participant_info.get("user_name")
                        or "User"
                    )
                else:
                    # Fallback: If only one participant, use their name
                    if len(self.participants_map) == 1:
                        single_participant = list(self.participants_map.values())[0]
                        speaker_name = (
                            single_participant.get("name")
                            or single_participant.get("user_name")
                            or "User"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Could not resolve speaker name for user_id: {msg_user_id}, "
                            f"participants_map has {len(self.participants_map)} participants. Using default 'User'"
                        )

            # Format and add to transcript text
            line = self._format_transcript_line(
                speaker_name, msg.content, msg.timestamp
            )
            self.transcript_text += line + "\n"

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
    sprites_dir = os.path.join(hosting_dir, "sprites")

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


class SpeakerTrackingProcessor(FrameProcessor):
    """
    Tracks speaker IDs from frames with speaker information.

    Extracts speaker IDs from frames (e.g., from Deepgram STT with diarization enabled).
    Maintains a mapping between speaker IDs and Daily.co participants.
    """

    def __init__(self, transcript_handler: Optional["TranscriptHandler"] = None):
        super().__init__()
        # Mapping: Deepgram speaker ID -> Daily.co session_id
        self.speaker_to_session_map: Dict[int, str] = {}
        # Track the last seen speaker ID from frames
        self.last_speaker: Optional[int] = None
        # Reference to transcript handler for participant order mapping
        self.transcript_handler: Optional["TranscriptHandler"] = transcript_handler

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and extract speaker IDs from frames with speaker information."""
        await super().process_frame(frame, direction)

        frame_type = type(frame).__name__
        logger.debug(f"📦 Frame received: {frame_type}")

        # Check if frame has speaker information (from Deepgram STT with diarization enabled)
        speaker_id = getattr(frame, "speaker", None) or getattr(
            frame, "speaker_id", None
        )

        # Log frame details when speaker info is present
        if speaker_id is not None:
            self.last_speaker = speaker_id
            logger.debug(f"📢 Frame with speaker ID: {speaker_id}, type: {frame_type}")

            # If this speaker ID isn't mapped yet, try to map it using participant order
            if (
                speaker_id not in self.speaker_to_session_map
                and self.transcript_handler
            ):
                # Get unmapped participants in join order
                mapped_session_ids = set(self.speaker_to_session_map.values())
                unmapped_participants = [
                    session_id
                    for session_id in self.transcript_handler.participant_join_order
                    if session_id not in mapped_session_ids
                    and session_id in self.transcript_handler.participants_map
                ]

                if unmapped_participants:
                    # Map to first unmapped participant
                    session_id = unmapped_participants[0]
                    self.map_speaker_to_participant(speaker_id, session_id)
                    logger.debug(
                        f"✅ Auto-mapped Deepgram speaker {speaker_id} → Daily.co session_id {session_id} "
                        f"(using participant order: {self.transcript_handler.participant_join_order})"
                    )

        # Pass frame through to next processor
        await self.push_frame(frame, direction)

    def map_speaker_to_participant(
        self, deepgram_speaker_id: int, daily_session_id: str
    ):
        """
        Map a Deepgram speaker ID to a Daily.co session_id.

        Args:
            deepgram_speaker_id: The speaker ID from Deepgram (0, 1, 2, etc.)
            daily_session_id: The session_id from Daily.co (peerId)
        """
        self.speaker_to_session_map[deepgram_speaker_id] = daily_session_id
        logger.info(
            f"✅ Speaker mapping: Deepgram {deepgram_speaker_id} → Daily.co {daily_session_id}"
        )

    def get_current_speaker_id(self) -> Optional[int]:
        """
        Get the last seen Deepgram speaker ID.

        Returns:
            The last seen speaker ID, or None if no speaker has been seen yet
        """
        return self.last_speaker

    def get_all_mappings(self) -> Dict[int, str]:
        """Get all current speaker ID to session_id mappings."""
        return self.speaker_to_session_map.copy()

    def log_mapping_summary(self):
        """Log a summary of current speaker mappings for diagnostics."""
        logger.info(f"📊 Current speaker mappings: {self.speaker_to_session_map}")
        logger.debug(f"   Last seen speaker ID: {self.last_speaker}")


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

    def __init__(
        self,
        room_name: str,
        task: asyncio.Task,
        transport: Optional["DailyTransport"] = None,
    ):
        self.room_name = room_name
        self.task = task
        self.transport = transport  # Store transport reference for cleanup
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
        # Simple Explanation: transport_map stores DailyTransport instances for each room
        # This allows us to explicitly leave the room during cleanup
        self.transport_map: Dict[str, "DailyTransport"] = {}

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
        workflow_thread_id: Optional[str] = None,
    ) -> bool:
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
                        self._run_bot(
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
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        room_name: str,
        workflow_thread_id: Optional[str] = None,
    ) -> None:
        """
        Run the Pipecat bot directly without subprocess.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            room_name: Room name for saving transcript to database
            workflow_thread_id: Optional workflow thread ID to associate with this bot session
        """
        try:

            # Get bot prompt from config - this defines what the bot should do/say
            # If not provided, use a generic default
            bot_prompt = bot_config.get(
                "bot_prompt",
                bot_config.get(
                    "system_message",
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

            # Store transport reference so we can explicitly leave the room during cleanup
            self.transport_map[room_name] = transport

            logger.info(
                f"Bot transport initialized for room: {room_url}, bot_name: {bot_name}"
            )

            # Load participants immediately after transport creation
            # This ensures we know all participants even if they joined before the bot
            initial_participants = transport.participants() or {}
            participants_map = {}
            for pid, pdata in initial_participants.items():
                if pid == "local":
                    continue
                session_id = pdata.get("session_id") or pid
                # Extract name from nested info object - Daily.co always provides info.userName
                info = pdata.get("info", {})
                name = info.get("userName") or f"Participant {session_id}"
                participants_map[session_id] = {
                    "session_id": session_id,
                    "name": name,
                    "user_id": pdata.get("user_id"),
                }
            logger.info(f"📋 Participants loaded at startup: {participants_map}")

            # Use OpenAI for both LLM and TTS
            llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4.1")
            tts = OpenAITTSService(
                api_key=os.getenv("OPENAI_API_KEY"),
                voice="alloy",
                interruptions_allowed=True,
                interruption_strategies=[MinWordsInterruptionStrategy(min_words=1)],
            )

            # Use Deepgram for Speech-to-Text (STT) to transcribe user speech
            # Enable speaker diarization to identify different speakers
            # utterances=True is required for proper speaker segments
            stt = DeepgramSTTService(
                api_key=os.getenv("DEEPGRAM_API_KEY"),
                model="nova-2",
                diarize=True,
                utterances=True,
            )
            logger.info("🎤 Deepgram STT initialized with diarization and utterances")
            logger.info("   🔍 DEBUG: Deepgram STT configuration:")
            logger.info("      - model: nova-2")
            logger.info("      - diarize: True")
            logger.info("      - utterances: True")
            logger.info(f"      - STT service type: {type(stt)}")

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

            # Get workflow_thread_id for this room (if workflow is running)
            # Simple Explanation: We need to find the workflow_thread_id so we can save
            # the transcript to workflow_threads table. Use the passed parameter if available,
            # otherwise look for a paused workflow for this room as fallback.
            if not workflow_thread_id:
                try:
                    from flow.db import get_workflow_threads_by_room_name

                    threads = get_workflow_threads_by_room_name(room_name)
                    # Get the most recent paused workflow thread
                    for thread in threads:
                        if thread.get("workflow_paused"):
                            workflow_thread_id = thread.get("workflow_thread_id")
                            break
                except Exception as e:
                    logger.debug(
                        f"Could not find workflow_thread_id for room {room_name}: {e}"
                    )

            # Create transcript handler first (needed for speaker tracker)
            transcript_handler = TranscriptHandler(
                room_name=room_name,
                bot_name=bot_name,
                speaker_tracker=None,  # Will be set after creation
                transport=transport,
                workflow_thread_id=workflow_thread_id,
            )

            # Create speaker tracking processor to extract speaker IDs from frames
            # Pass transcript_handler reference for participant order mapping
            speaker_tracker = SpeakerTrackingProcessor(
                transcript_handler=transcript_handler
            )

            # Now set the speaker_tracker reference in transcript_handler
            transcript_handler.speaker_tracker = speaker_tracker
            # Set participants_map that was loaded at startup
            transcript_handler.participants_map = participants_map
            logger.info(
                f"📝 Transcript will be saved to database for room: {room_name}\n"
                "   - User speech: Deepgram STT (from pipeline) with speaker diarization\n"
                "   - Bot speech: TranscriptProcessor (from TTS input)"
            )

            # Load video frames based on bot configuration
            quiet_frame, talking_frame = load_bot_video_frames(bot_config)
            ta = TalkingAnimation(quiet_frame=quiet_frame, talking_frame=talking_frame)

            # Build pipeline with Deepgram STT and TranscriptProcessor
            pipeline_components = [
                transport.input(),  # Transport user input
                stt,  # Deepgram STT - converts user speech to text
                speaker_tracker,  # Track speaker IDs from frames
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
                """Log when any participant (including bot) joins and update participants map."""
                participant_id = participant.get("id", "unknown")
                participant_name = participant.get("user_name", "unknown")
                is_local = participant.get("local", False)
                session_id = participant.get("session_id") or participant_id

                logger.info(
                    f"🔵 Participant joined - ID: {participant_id}, Name: {participant_name}, Local: {is_local}, Session ID: {session_id}"
                )

                # Update participants map
                # Get all participants from Daily.co
                try:
                    participants = transport.participants()
                    if not participants:
                        logger.warning(
                            "⚠️ No participants returned from transport.participants()"
                        )
                        return

                    # Identify bot's session_id (local participant or match by bot_name)
                    bot_session_id = None
                    if is_local:
                        bot_session_id = session_id
                    else:
                        # Check if this participant matches bot_name
                        if participant_name == bot_name:
                            bot_session_id = session_id

                    if bot_session_id:
                        transcript_handler.bot_session_id = bot_session_id

                    # Build participants_map for all NON-bot participants
                    participants_map = {}
                    for pid, pdata in participants.items():
                        if pid == "local":
                            # Skip local participant (it's the bot)
                            continue
                        p_session_id = pdata.get("session_id") or pid
                        # Skip bot if we've identified it
                        if bot_session_id and p_session_id == bot_session_id:
                            continue
                        # Skip if this is the bot by name
                        # Extract name from nested info object - Daily.co always provides info.userName
                        info = pdata.get("info", {})
                        p_name = info.get("userName") or ""
                        if p_name == bot_name:
                            continue

                        participants_map[p_session_id] = {
                            "name": p_name,
                            "user_name": p_name,  # Add for consistency/backward compatibility
                            "user_id": pdata.get("user_id"),
                            "session_id": p_session_id,
                            "id": pid,
                        }

                    transcript_handler.participants_map = participants_map
                    # Update participant join order (preserve existing order, add new participants)
                    for session_id in participants_map.keys():
                        if session_id not in transcript_handler.participant_join_order:
                            transcript_handler.participant_join_order.append(session_id)
                    logger.info(
                        f"📋 Participants map updated: {len(participants_map)} participant(s)"
                    )

                    # Log participant counts after updating participants map
                    try:
                        counts = transport.participant_counts()
                        if counts:
                            present = counts.get("present", 0)
                            hidden = counts.get("hidden", 0)
                            total = present + hidden
                            logger.info(
                                f"👥 Participant counts after join - Present: {present}, Hidden: {hidden}, Total: {total}"
                            )
                        else:
                            logger.debug("Participant counts not available after join")
                    except Exception as count_error:
                        logger.warning(
                            f"⚠️ Error getting participant counts after join: {count_error}"
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Error updating participants map: {e}", exc_info=True
                    )

            # Register event handler for active speaker changes
            @transport.event_handler("on_active_speaker_changed")
            async def on_active_speaker_changed(transport, event):
                """Handle active speaker change events to map Deepgram speaker IDs to Daily.co participants."""
                active_speaker = (
                    event.get("activeSpeaker", {})
                    if isinstance(event, dict)
                    else getattr(event, "activeSpeaker", {})
                )

                # Try to get peer_id from activeSpeaker.peerId first
                peer_id = (
                    active_speaker.get("peerId")
                    if isinstance(active_speaker, dict)
                    else getattr(active_speaker, "peerId", None)
                )

                # Fallback: Use event.id (Daily.co participant ID) if peerId not available
                if not peer_id:
                    event_id = (
                        event.get("id")
                        if isinstance(event, dict)
                        else getattr(event, "id", None)
                    )
                    if event_id:
                        peer_id = event_id
                    else:
                        logger.debug(
                            "No peerId or event.id in on_active_speaker_changed event"
                        )
                        return

                # Get current Deepgram speaker ID
                deepgram_speaker_id = speaker_tracker.get_current_speaker_id()

                if deepgram_speaker_id is not None:
                    speaker_tracker.map_speaker_to_participant(
                        deepgram_speaker_id, peer_id
                    )
                    logger.debug(
                        f"Mapped Deepgram speaker {deepgram_speaker_id} → Daily.co session_id {peer_id}"
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
                # Get participant counts from transport
                # Simple Explanation: participant_counts() returns information about
                # how many participants are currently in the room (present and hidden).
                counts = transport.participant_counts()
                if counts:
                    present = counts.get("present", 0)
                    hidden = counts.get("hidden", 0)
                    logger.info(
                        f"👥 Participant counts updated - Present: {present}, Hidden: {hidden}"
                    )
                else:
                    logger.debug("Participant counts not available")

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

                # Check participant counts before deciding whether to leave
                # Simple Explanation: We only want the bot to leave when it's the only
                # present participant remaining (present count = 1). If other participants
                # are still present, we should stay in the room and continue the conversation.
                # Hidden participants don't affect this decision - only present participants matter.
                try:
                    counts = transport.participant_counts()
                    if counts:
                        present = counts.get("present", 0)
                        hidden = counts.get("hidden", 0)
                        logger.info(
                            f"👥 Participant counts after leave - Present: {present}, Hidden: {hidden}"
                        )

                        # Only check present count for decision - hidden participants don't matter
                        # Simple Explanation: If present count > 1, it means there are other
                        # present participants besides the bot. We should stay in the room and not
                        # proceed with cleanup/workflow resume. Hidden participants are ignored.
                        if present > 1:
                            logger.info(
                                f"✅ Bot staying in room - {present} present participant(s) still in room (including bot)"
                            )
                            return  # Early return - don't proceed with cleanup
                        elif present == 1:
                            logger.info(
                                "🚪 Only bot remains as present participant - proceeding with cleanup and workflow resume"
                            )
                        else:
                            # Count is 0 or None - this shouldn't happen, but log a warning
                            logger.warning(
                                f"⚠️ Unexpected present participant count: {present} - proceeding with cleanup anyway"
                            )
                    else:
                        # If participant_counts() returns None, log warning but proceed (fail-safe)
                        logger.warning(
                            "⚠️ Could not get participant counts - proceeding with cleanup (fail-safe behavior)"
                        )
                except Exception as count_error:
                    # If there's an error getting counts, log warning but proceed (fail-safe)
                    logger.warning(
                        f"⚠️ Error getting participant counts: {count_error} - proceeding with cleanup (fail-safe behavior)"
                    )

                # Check if there's a workflow waiting to resume
                # Simple Explanation: If a workflow was started via the bot_call
                # workflow, it will have a workflow_thread_id. First try to use the
                # workflow_thread_id stored in transcript_handler (most reliable), then
                # check session_data (for backward compatibility), and finally lookup by room_name.
                from flow.db import get_session_data, get_workflow_thread_data

                # First try to use workflow_thread_id from transcript_handler (most reliable)
                workflow_thread_id = (
                    transcript_handler.workflow_thread_id
                    if transcript_handler.workflow_thread_id
                    else None
                )

                # If not found, try to get workflow_thread_id from session_data (for backward compatibility)
                if not workflow_thread_id:
                    session_data = get_session_data(room_name) or {}
                    workflow_thread_id = session_data.get("workflow_thread_id")

                # If still not found, try to find it from workflow_threads by room_name (fallback)
                if not workflow_thread_id:
                    from flow.db import get_workflow_threads_by_room_name

                    threads = get_workflow_threads_by_room_name(room_name)
                    # Get the most recent paused workflow thread
                    for thread in threads:
                        if thread.get("workflow_paused"):
                            workflow_thread_id = thread.get("workflow_thread_id")
                            break

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

                        # Retrieve checkpoint_id from workflow_threads if available
                        # Simple Explanation: The checkpoint_id tells LangGraph exactly which
                        # checkpoint to resume from. Without it, LangGraph might resume from
                        # the wrong checkpoint or restart from the beginning.
                        workflow_thread_data = get_workflow_thread_data(
                            workflow_thread_id
                        )
                        checkpoint_id = (
                            workflow_thread_data.get("checkpoint_id")
                            if workflow_thread_data
                            else None
                        )

                        # Build config with thread_id and checkpoint_id (if available)
                        config = {"configurable": {"thread_id": workflow_thread_id}}
                        if checkpoint_id:
                            config["configurable"]["checkpoint_id"] = checkpoint_id
                            logger.info(
                                f"   📍 Resuming from checkpoint_id: {checkpoint_id}"
                            )
                        else:
                            logger.warning(
                                "   ⚠️ No checkpoint_id found - workflow may restart from beginning"
                            )

                        # Simple Explanation: LangGraph automatically resumes from the specified
                        # checkpoint when you call ainvoke with a config containing both thread_id
                        # and checkpoint_id. When resuming from a static interrupt (interrupt_after),
                        # you should pass None - LangGraph will use the state from the checkpoint
                        # and continue to the next node (process_transcript). The checkpoint already
                        # has all the state from when the workflow paused, so we don't need to pass anything.
                        # Resume the workflow - it will continue to process_transcript node
                        graph = await workflow.graph

                        # Try to get the checkpoint state first to verify it exists
                        # Simple Explanation: This helps us detect if the checkpoint is missing
                        # (e.g., if using MemorySaver and server restarted, or if checkpointer isn't configured)
                        try:
                            state_snapshot = await graph.aget_state(config)
                            if not state_snapshot or not state_snapshot.values:
                                raise ValueError(
                                    "Checkpoint state not found. This may happen if: "
                                    "1) Using in-memory checkpointer and server restarted, "
                                    "2) SUPABASE_DB_PASSWORD is not set in .env file, "
                                    "3) Checkpoint was deleted or expired."
                                )
                            logger.info(
                                "   ✅ Checkpoint state found - resuming workflow"
                            )
                        except Exception as state_error:
                            logger.warning(
                                f"   ⚠️ Could not retrieve checkpoint state: {state_error}"
                            )
                            logger.warning(
                                "   This usually means the checkpointer isn't configured properly. "
                                "Check that SUPABASE_DB_PASSWORD is set in your .env file."
                            )
                            raise

                        # Pass None to resume from static interrupt - LangGraph will use checkpoint state and continue to next node
                        await graph.ainvoke(None, config=config)
                        logger.info("✅ Workflow resumed successfully")
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(
                            f"❌ Error resuming workflow: {error_msg}", exc_info=True
                        )

                        # Provide helpful error message if it's a checkpointer issue
                        if (
                            "SUPABASE_DB" in error_msg.upper()
                            or "checkpoint" in error_msg.lower()
                        ):
                            logger.error(
                                "   💡 TIP: This error is likely due to missing Supabase database credentials. "
                                "Add SUPABASE_DB_PASSWORD to your .env file. "
                                "Run: python scripts/diagnose_supabase.py to check your configuration."
                            )

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
                    # Explicitly leave the room before cleanup
                    logger.info(f"🚪 Leaving Daily.co room: {room_name}")
                    await transport.cleanup()
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
                finally:
                    # Remove transport from map after cleanup
                    self.transport_map.pop(room_name, None)

        except asyncio.CancelledError:
            # Task was cancelled - this is expected when participant leaves or during shutdown
            logger.info("🛑 Bot task was cancelled - ensuring bot leaves the room")
            # Ensure transport is cleaned up even on cancellation - this is critical to leave the room
            try:
                if "transport" in locals():
                    logger.info(
                        f"🚪 Leaving Daily.co room on cancellation: {room_name}"
                    )
                    await transport.cleanup()
                    logger.info("✅ Transport cleaned up after cancellation")
            except (RuntimeError, asyncio.CancelledError) as e:
                # Ignore "Event loop is closed" errors during cancellation - these are expected
                if "Event loop is closed" not in str(e):
                    logger.debug(f"Transport cleanup during cancellation: {e}")
            except Exception as e:
                logger.warning(f"Error during transport cleanup on cancellation: {e}")
            finally:
                # Remove transport from map after cleanup
                self.transport_map.pop(room_name, None)
            raise
        except Exception as e:
            logger.error(f"❌ Bot process error: {e}", exc_info=True)
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error message: {str(e)}")
            # Ensure transport is cleaned up even on error - must leave the room
            try:
                if "transport" in locals():
                    logger.info(f"🚪 Leaving Daily.co room after error: {room_name}")
                    await transport.cleanup()
                    logger.info("✅ Transport cleaned up after error")
            except (RuntimeError, asyncio.CancelledError) as cleanup_e:
                # Ignore "Event loop is closed" errors during error handling - these are expected
                if "Event loop is closed" not in str(cleanup_e):
                    logger.debug(f"Transport cleanup during error: {cleanup_e}")
            except Exception as cleanup_e:
                logger.warning(
                    f"Error during transport cleanup after error: {cleanup_e}"
                )
            finally:
                # Remove transport from map after cleanup
                self.transport_map.pop(room_name, None)
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
            # automatically retrieve transcript_text from the database if not provided.
            # We also pass workflow_thread_id if available so processing status can be tracked per workflow run.
            from flow.db import get_session_data

            session_data = get_session_data(room_name) or {}
            workflow_thread_id = session_data.get("workflow_thread_id")

            state = {
                "room_name": room_name,
                "workflow_thread_id": workflow_thread_id,
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
            if room_name in self.bot_id_map:
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
        """Stop all running bots and ensure they leave the room."""
        logger.info(f"Cleaning up {len(self.active_bots)} bots...")

        # First, try to explicitly leave the room for each bot before cancelling
        # This ensures the bot leaves the Daily.co room even if cancellation is abrupt
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
                except asyncio.TimeoutError:
                    logger.warning(
                        f"⚠️ Timeout leaving room {room_name}, proceeding with cancellation"
                    )
                except (RuntimeError, asyncio.CancelledError) as e:
                    # Ignore "Event loop is closed" errors - these are expected during shutdown
                    if "Event loop is closed" not in str(e):
                        logger.debug(f"Error leaving room {room_name}: {e}")
                except Exception as e:
                    logger.warning(f"Error leaving room {room_name}: {e}")

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
