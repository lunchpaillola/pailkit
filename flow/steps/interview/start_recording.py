# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Start Recording Step

This step starts recording and transcription for the interview.
"""

import logging
import uuid
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class StartRecordingStep(InterviewStep):
    """
    Start recording and transcription for the interview.

    **Simple Explanation:**
    This step starts recording the video/audio and begins transcribing
    everything that's said during the interview. It's like pressing the
    record button and turning on live captions.
    """

    def __init__(self):
        super().__init__(
            name="start_recording",
            description="Start recording and transcription for the interview",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute recording and transcription start.

        Args:
            state: Current workflow state containing room_id and provider_keys

        Returns:
            Updated state with recording_id and transcription_id
        """
        # Validate required state
        if not self.validate_state(state, ["room_id"]):
            return self.set_error(
                state, "Room ID is required to start recording/transcription"
            )

        # TODO: Use provider_keys when implementing actual provider integration
        # provider_keys = state.get("provider_keys", {})
        # transcription_provider_key = provider_keys.get("transcription_provider_key")
        # transcription_provider = provider_keys.get("transcription_provider", "daily")
        room_id = state.get("room_id")

        logger.info(f"🎙️ Starting recording and transcription for room {room_id}")

        try:
            # TODO: Replace with actual recording/transcription provider integration
            # This would make API calls to start recording and transcription
            # For now, we'll simulate it

            recording_id = str(uuid.uuid4())
            transcription_id = str(uuid.uuid4())

            state["recording_id"] = recording_id
            state["transcription_id"] = transcription_id
            state = self.update_status(state, "recording_started")

            logger.info(f"✅ Recording started: {recording_id}")
            logger.info(f"✅ Transcription started: {transcription_id}")

        except Exception as e:
            error_msg = f"Failed to start recording/transcription: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        return state
