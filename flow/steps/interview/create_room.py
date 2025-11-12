# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Create Room Step

This step creates a video room for the interview using the room provider.
"""

import logging
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class CreateRoomStep(InterviewStep):
    """
    Create a video room for the interview.

    **Simple Explanation:**
    This step creates a video room (like a Zoom meeting) where the interview
    will take place. It uses the rooms API to set up a room with recording
    and transcription enabled.
    """

    def __init__(self):
        super().__init__(
            name="create_room",
            description="Create video room with recording and transcription enabled",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute room creation.

        Args:
            state: Current workflow state containing provider_keys and session_id

        Returns:
            Updated state with room_id and room_url
        """
        # Validate required state
        if not self.validate_state(state, ["provider_keys", "session_id"]):
            return self.set_error(
                state, "Missing required state: provider_keys or session_id"
            )

        provider_keys = state.get("provider_keys", {})
        room_provider_key = provider_keys.get("room_provider_key")
        room_provider = provider_keys.get("room_provider", "daily")

        if not room_provider_key:
            return self.set_error(state, "Missing room_provider_key in provider_keys")

        logger.info(f"📹 Creating video room with provider: {room_provider}")

        try:
            # TODO: Replace with actual room provider integration
            # This would call the rooms API or use a provider client
            # For now, we'll simulate the room creation

            session_id = state.get("session_id", "unknown")
            room_name = f"interview-{session_id}"
            room_url = f"https://{room_provider}.example.com/{room_name}"
            room_id = room_name

            state["room_id"] = room_id
            state["room_url"] = room_url
            state = self.update_status(state, "room_created")

            logger.info(f"✅ Video room created: {room_url}")

        except Exception as e:
            error_msg = f"Failed to create video room: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        return state
