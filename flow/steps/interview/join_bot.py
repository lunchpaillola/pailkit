# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Join Bot Step - Configures and triggers AI bot to join meeting."""

import logging
from typing import Any, Dict

from flow.steps.interview.bot_service import bot_service

logger = logging.getLogger(__name__)


class JoinBotStep:
    """Step to join an AI bot to the created meeting room."""

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Configure bot to join the created room."""
        try:
            bot_config = state.get("meeting_config", {}).get("bot", {})

            if bot_config.get("enabled"):
                room_url = state.get("room_url")
                meeting_token = state.get("meeting_token")
                room_name = state.get("room_name")

                if not room_url:
                    state["error"] = "Room URL not available for bot to join"
                    state["bot_joined"] = False
                    return state

                # Start the actual bot service
                success = await bot_service.start_bot(
                    room_url, meeting_token, bot_config
                )

                if success:
                    state["bot_joined"] = True
                    state["bot_config"] = bot_config
                    logger.info(f"Bot started successfully for room: {room_name}")
                else:
                    state["bot_joined"] = False
                    state["error"] = "Failed to start bot service"
                    logger.error(f"Failed to start bot for room: {room_name}")

            else:
                state["bot_joined"] = False
                logger.info("Bot disabled in configuration")

            return state

        except Exception as e:
            logger.error(f"Error in JoinBotStep: {e}", exc_info=True)
            state["error"] = f"Failed to configure bot: {str(e)}"
            state["bot_joined"] = False
            return state
