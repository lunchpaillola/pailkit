# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Transcript handler for processing and storing transcripts."""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

if TYPE_CHECKING:
    from pipecat.transports.daily.transport import DailyTransport
    from flow.steps.agent_call.bot.speaker_tracking import SpeakerTrackingProcessor

from pipecat.frames.frames import TranscriptionMessage, TranscriptionUpdateFrame
from pipecat.processors.transcript_processor import TranscriptProcessor

logger = logging.getLogger(__name__)


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
