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
        """Build Daily.co API configuration for interview room."""
        daily_properties: Dict[str, Any] = {
            "enable_recording": "cloud",
            "enable_transcription_storage": True,
            "enable_prejoin_ui": True,
            "enable_chat": True,
            "enable_screenshare": True,
        }

        config: Dict[str, Any] = {
            "properties": daily_properties,
            "privacy": "public",
        }

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

    async def _create_daily_token(self, api_key: str, room_name: str) -> str | None:
        """Create a Daily.co meeting token with transcription admin permissions."""
        headers = self._get_daily_headers(api_key)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.daily.co/v1/meeting-tokens",
                    headers=headers,
                    json={
                        "properties": {
                            "room_name": room_name,
                            "is_owner": True,
                            "permissions": {
                                "canAdmin": ["transcription"],
                            },
                        },
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("token")
        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                logger.warning(f"Failed to create meeting token: {error_data}")
            except Exception:
                logger.warning(f"Failed to create meeting token: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to create meeting token: {e}")
            return None

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
                logger.error(
                    f"Daily.co API error: {error_detail} (status: {e.response.status_code})"
                )
            except Exception:
                error_detail = str(e)
                logger.error(f"Daily.co API error: {error_detail}")

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

            room_name = result.get("room_name")

            # Create a token with transcription admin permissions for auto-start
            meeting_token = await self._create_daily_token(room_provider_key, room_name)
            if meeting_token:
                logger.info(
                    f"✅ Meeting token created with transcription admin permissions: {meeting_token[:20]}..."
                )
            else:
                logger.warning(
                    "⚠️ Meeting token creation failed - transcription may not auto-start"
                )

            state["room_id"] = result.get("room_id")
            state["room_url"] = room_url
            state["room_name"] = room_name
            state["room_provider"] = room_provider
            if meeting_token:
                state["meeting_token"] = meeting_token

            if branding:
                state["branding"] = branding

            state = self.update_status(state, "room_created")
            logger.info(f"✅ Video room created: {room_url}")

        except Exception as e:
            error_msg = f"Failed to create video room: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return self.set_error(state, error_msg)

        return state
