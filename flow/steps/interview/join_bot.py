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
        logger.info("🟢 JoinBotStep.execute() called")
        logger.info(f"   State keys: {list(state.keys())}")
        try:
            meeting_config = state.get("meeting_config", {})
            logger.info(
                f"   meeting_config keys: {list(meeting_config.keys()) if meeting_config else 'None'}"
            )
            logger.info(f"   meeting_config.get('bot'): {meeting_config.get('bot')}")
            bot_config = meeting_config.get("bot", {})
            logger.info(f"   bot_config: {bot_config}")
            logger.info(f"   bot_config.get('enabled'): {bot_config.get('enabled')}")

            if bot_config.get("enabled"):
                room_url = state.get("room_url")
                meeting_token = state.get("meeting_token")
                room_name = state.get("room_name")
                logger.info(f"   room_url: {room_url}")
                logger.info(
                    f"   meeting_token: {meeting_token[:20] if meeting_token else None}..."
                )
                logger.info(f"   room_name: {room_name}")

                if not room_url:
                    logger.error("❌ Room URL not available for bot to join")
                    state["error"] = "Room URL not available for bot to join"
                    state["bot_joined"] = False
                    return state

                # Start the actual bot service
                # Note: When bot is enabled, TranscriptProcessor in bot_service.py
                # will handle transcription of both user and bot automatically
                logger.info("📞 Calling bot_service.start_bot()...")
                success = await bot_service.start_bot(
                    room_url, meeting_token, bot_config, room_name
                )
                logger.info(f"   bot_service.start_bot() returned: {success}")

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
