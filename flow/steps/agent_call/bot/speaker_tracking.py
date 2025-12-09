# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Speaker tracking processor for identifying speakers in audio frames."""

import logging
from typing import TYPE_CHECKING, Dict, Optional

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

if TYPE_CHECKING:
    from flow.steps.agent_call.bot.transcript_handler import TranscriptHandler

logger = logging.getLogger(__name__)


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
