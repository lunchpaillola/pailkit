# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Create Room Step

Creates a Daily.co video room for the interview with recording and transcription enabled.
"""

import logging
from typing import Any, Dict

import httpx

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class CreateRoomStep(InterviewStep):
    """Create a Daily.co video room for the interview."""

    def __init__(self):
        super().__init__(
            name="create_room",
            description="Create video room with recording and transcription enabled",
        )

    def _build_daily_config(self, interview_config: Dict[str, Any]) -> Dict[str, Any]:
        """Build Daily.co API configuration from interview config."""
        daily_properties: Dict[str, Any] = {
            "enable_recording": "cloud",
            "enable_transcription_storage": True,
            "auto_transcription_settings": {
                "language": "en",
                "model": "nova-2",
                "punctuate": True,
                "profanity_filter": False,
            },
            "enable_prejoin_ui": True,
            "enable_chat": False,
        }

        if interview_config.get("live_captions"):
            daily_properties["enable_live_captions_ui"] = True

        room_settings = interview_config.get("room_settings", {})
        if room_settings:
            capabilities = room_settings.get("capabilities", {})
            media = room_settings.get("media", {})
            access = room_settings.get("access", {})

            if "chat" in capabilities:
                daily_properties["enable_chat"] = capabilities["chat"]
            if "recording" in capabilities:
                daily_properties["enable_recording"] = (
                    "cloud" if capabilities["recording"] else False
                )
            if "screenshare" in capabilities:
                daily_properties["enable_screenshare"] = capabilities["screenshare"]
            if "video" in media and not media["video"]:
                daily_properties["start_video_off"] = True
            if "screenshare_capable" in media:
                daily_properties["enable_screenshare"] = media["screenshare_capable"]

            privacy = access.get("privacy", "public")
            max_participants = access.get("max_participants")
        else:
            privacy = "public"
            max_participants = None

        config: Dict[str, Any] = {
            "properties": daily_properties,
            "privacy": privacy,
        }
        if max_participants is not None:
            config["max_participants"] = max_participants

        return config

    def _get_daily_headers(self, api_key: str) -> Dict[str, str]:
        """Get HTTP headers for Daily.co API requests."""
        auth_header = api_key.strip()
        if not auth_header.startswith("Bearer "):
            auth_header = f"Bearer {auth_header}"

        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }

    async def _create_daily_room(
        self, api_key: str, daily_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a room using Daily.co's API."""
        headers = self._get_daily_headers(api_key)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.daily.co/v1/rooms",
                    headers=headers,
                    json=daily_config,
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

                room_url = result.get("url", "")
                room_name = room_url.split("/")[-1] if room_url else ""

                return {
                    "success": True,
                    "room_id": result.get("id"),
                    "room_name": room_name,
                    "room_url": room_url,
                    "created_at": result.get("created_at"),
                    "config": result.get("config", {}),
                    "privacy": result.get("privacy"),
                    "message": "Room created successfully",
                }

        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("error", str(e))
            except Exception:
                error_detail = str(e)

            return {
                "success": False,
                "room_id": None,
                "room_name": None,
                "room_url": None,
                "message": f"Daily API error: {error_detail}",
            }
        except Exception as e:
            return {
                "success": False,
                "room_id": None,
                "room_name": None,
                "room_url": None,
                "message": f"Failed to create room: {str(e)}",
            }

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute room creation."""
        if not self.validate_state(state, ["provider_keys", "session_id"]):
            return self.set_error(
                state, "Missing required state: provider_keys or session_id"
            )

        provider_keys = state.get("provider_keys", {})
        room_provider_key = provider_keys.get("room_provider_key")
        room_provider = provider_keys.get("room_provider", "daily").lower()

        if not room_provider_key:
            return self.set_error(state, "Missing room_provider_key in provider_keys")

        if room_provider != "daily":
            return self.set_error(state, f"Unsupported room provider: {room_provider}")

        interview_config = state.get("interview_config") or state.get(
            "meeting_config", {}
        )
        branding = interview_config.get("branding", {})

        logger.info(f"📹 Creating video room (session: {state.get('session_id')})")

        try:
            daily_config = self._build_daily_config(interview_config)
            result = await self._create_daily_room(room_provider_key, daily_config)

            if not result.get("success"):
                error_msg = result.get("message", "Unknown error creating room")
                logger.error(f"❌ Daily API error: {error_msg}")
                return self.set_error(
                    state, f"Failed to create video room: {error_msg}"
                )

            room_url = result.get("room_url")
            if not room_url:
                return self.set_error(state, "Room created but no room_url returned")

            state["room_id"] = result.get("room_id")
            state["room_url"] = room_url
            state["room_name"] = result.get("room_name")
            state["room_provider"] = room_provider

            if branding:
                state["branding"] = branding

            state = self.update_status(state, "room_created")
            logger.info(f"✅ Video room created: {room_url}")

        except Exception as e:
            error_msg = f"Failed to create video room: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return self.set_error(state, error_msg)

        return state
