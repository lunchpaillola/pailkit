# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Create Room Step

Creates a Daily.co video room for the interview with recording and transcription enabled.
"""

import logging
import os
import time
from datetime import datetime
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
        """
        Build Daily.co API configuration for interview room.

        **Simple Explanation:**
        This method creates the configuration that tells Daily.co how to set up the room.
        It includes basic settings like recording and transcription. If VAPI calling is enabled,
        we'll enable PIN dial-in after room creation so VAPI can join the room by dialing
        the phone number and entering the PIN via DTMF.

        If STAGING_ENVIRONMENT is set to "DEVELOPMENT", it will add a unique room name
        in the format DEV-DDMMYYYYHHMMSSFFFFFF (e.g., DEV-15012025143022123456 for Jan 15, 2025 at 14:30:22.123456).
        The microseconds ensure uniqueness even with multiple requests per second.
        """
        daily_properties: Dict[str, Any] = {
            "enable_recording": "cloud",
            "enable_transcription_storage": True,
            "enable_prejoin_ui": True,
            "enable_chat": True,
            "enable_screenshare": True,
        }

        # Note: We don't set SIP properties during room creation
        # **Simple Explanation:** According to Daily.co docs, SIP properties should be set
        # by updating the room AFTER creation, not during initial creation
        # We'll enable SIP dial-in after the room is created (in execute method)

        config: Dict[str, Any] = {
            "properties": daily_properties,
            "privacy": "public",
        }

        # **Simple Explanation:** If we're in development mode, we need to set a unique room name.
        # Daily.co requires room names to be unique. We generate a name based on the current
        # date and time in the format DEV-DDMMYYYYHHMMSSFFFFFF (e.g., DEV-15012025143022123456).
        # The microseconds (FFFFFF) ensure uniqueness even if multiple rooms are created in the same second.
        # This ensures each room has a unique name that starts with "dev" so the webhook router
        # knows to route it to the development endpoint.
        staging_environment = os.getenv("STAGING_ENVIRONMENT", "").upper()
        if staging_environment == "DEVELOPMENT":
            # Generate unique name: DEV-DDMMYYYYHHMMSSFFFFFF (24-hour format + microseconds)
            # Example: DEV-15012025143022123456 = Jan 15, 2025 at 14:30:22.123456
            # Microseconds (6 digits) allow up to 1 million unique rooms per second
            now = datetime.now()
            room_name = now.strftime("DEV-%d%m%Y%H%M%S%f")
            config["name"] = room_name
            logger.info(f"🔧 Development mode: Setting unique room name to {room_name}")

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

    async def _update_room_for_pin_dialin(
        self, api_key: str, room_name: str, display_name: str = "Phone Caller"
    ) -> Dict[str, Any] | None:
        """
        Update room properties to enable PIN dial-in (following Daily.co guide).

        **Simple Explanation:**
        According to Daily.co docs, we update the room properties directly with a POST request.
        This enables PIN dial-in and returns the dial-in code (PIN). Daily.co will:
        1. Configure the room for PIN dial-in mode
        2. Generate a dial-in code (PIN) that callers need to enter
        3. Return the PIN so we can use it for VAPI calling via DTMF

        Args:
            api_key: Daily.co API key
            room_name: Name of the room to enable dial-in for
            display_name: Display name for phone participants

        Returns:
            Dictionary with dialin_code (PIN), or None if failed
        """
        headers = self._get_daily_headers(api_key)

        # Calculate expiration timestamp (1 year from now)
        # **Simple Explanation:** Daily.co requires an expiration timestamp (exp) for PIN dial-in
        # We set it to 1 year from now (365 days = 31536000 seconds)
        exp_timestamp = int(time.time()) + 31536000  # 1 year from now

        # Build the request payload following Daily.co guide format
        # **Simple Explanation:** This matches the curl example from Daily.co docs
        # We set dialin properties with display_name and wait_for_meeting_start
        # The exp field sets when the dial-in will expire (required field)
        properties = {
            "dialin": {
                "display_name": display_name,
                "wait_for_meeting_start": True,
            },
            "exp": exp_timestamp,
        }

        payload = {
            "properties": properties,
        }

        try:
            async with httpx.AsyncClient() as client:
                # Update room using POST to /v1/rooms/{room_name} as per Daily.co guide
                # **Simple Explanation:** We POST to update the room properties with PIN dial-in settings
                response = await client.post(
                    f"https://api.daily.co/v1/rooms/{room_name}",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

                # Extract dial-in code (PIN) from the response
                # **Simple Explanation:** Daily.co returns the dial-in code in config.dialin_code
                # This is the PIN that callers need to enter when dialing into the room
                config = result.get("config", {})
                dialin_code = config.get("dialin_code")

                if dialin_code:
                    logger.info(f"✅ PIN dial-in enabled: PIN code is {dialin_code}")
                    return {
                        "dialin_code": dialin_code,
                    }
                else:
                    logger.warning(
                        f"PIN dial-in enabled but dialin_code missing. "
                        f"Response: {result}"
                    )
                    return None

        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                logger.warning(f"Failed to enable PIN dial-in: {error_data}")
            except Exception:
                logger.warning(f"Failed to enable PIN dial-in: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to enable PIN dial-in: {e}")
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

            # Enable PIN dial-in if VAPI calling is enabled
            # **Simple Explanation:** If VAPI is enabled, we need to enable PIN dial-in
            # so that VAPI can join the room by dialing the phone number and entering the PIN.
            # This gives us a dial-in code (PIN) that VAPI will use via DTMF to join the room.
            vapi_config = interview_config.get("vapi", {})
            enable_vapi_calling = vapi_config.get("enabled", False)

            if enable_vapi_calling:
                # Get display name for phone participants
                display_name = (
                    branding.get("display_name") if branding else "Phone Caller"
                )

                # Update room to enable PIN dial-in and get dial-in code (PIN)
                # **Simple Explanation:** We update the room properties after creation
                # to enable PIN dial-in, following Daily.co's guide approach
                pin_result = await self._update_room_for_pin_dialin(
                    room_provider_key, room_name, display_name
                )

                if pin_result:
                    # Store dial-in code (PIN) in state for VAPI to use
                    # **Simple Explanation:** VAPI needs the PIN to dial into the room using DTMF
                    state["dialin_code"] = pin_result.get("dialin_code")
                    logger.info(
                        f"✅ PIN dial-in enabled: PIN code is {state['dialin_code']}"
                    )
                else:
                    logger.warning(
                        "⚠️ Failed to enable PIN dial-in - VAPI calling may not work"
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

            # Save session data to SQLite database
            # **Simple Explanation:** We store session data (candidate info, webhook URLs, etc.)
            # in our local SQLite database. This data will be retrieved later by the webhook
            # handler when the transcript is ready, so it knows where to send results.
            candidate_info = state.get("candidate_info", {})

            # Get interviewer_context from state (if configure_agent already ran) or from interview_config
            interviewer_context = (
                state.get("interviewer_context")
                or interview_config.get("interviewer_context")
                or ""
            )

            # Check if bot is enabled in meeting_config
            bot_enabled = False
            if "bot" in interview_config and isinstance(interview_config["bot"], dict):
                bot_enabled = interview_config["bot"].get("enabled", False)
            elif "bot_enabled" in interview_config:
                bot_enabled = interview_config.get("bot_enabled", False)

            # Check if frontend transcription is enabled (autoTranscribe)
            auto_transcribe = interview_config.get(
                "autoTranscribe", interview_config.get("auto_transcribe", False)
            )

            # Determine what webhook we're waiting for based on configuration
            # **Simple Explanation:**
            # - If bot is enabled: Bot saves transcript to DB, so we wait for meeting.ended
            # - If frontend transcription is enabled: Daily.co transcribes, so we wait for transcript.ready-to-download
            # - These flags tell the webhook handlers what to do
            waiting_for_meeting_ended = bot_enabled
            waiting_for_transcript_webhook = auto_transcribe and not bot_enabled

            session_data = {
                "webhook_callback_url": interview_config.get("webhook_callback_url"),
                "email_results_to": interview_config.get("email_results_to"),
                "candidate_name": candidate_info.get("name"),
                "candidate_email": candidate_info.get("email"),
                "position": candidate_info.get("role"),
                "interviewer_context": interviewer_context,
                "session_id": state.get("session_id"),
                "interview_type": interview_config.get("interview_type"),
                "difficulty_level": interview_config.get("difficulty_level"),
                "bot_enabled": bot_enabled,  # Track if bot is enabled
                "waiting_for_meeting_ended": waiting_for_meeting_ended,  # Bot enabled → wait for meeting.ended
                "waiting_for_transcript_webhook": waiting_for_transcript_webhook,  # Frontend transcription → wait for transcript webhook
                "meeting_status": "in_progress",  # Track meeting status
            }

            # Remove None values and empty strings to keep session data clean
            # But keep boolean flags and meeting_status even if False/empty string
            filtered_data = {}
            for k, v in session_data.items():
                if v is not None:
                    # Keep boolean flags and meeting_status even if False/empty string
                    if k in [
                        "bot_enabled",
                        "waiting_for_meeting_ended",
                        "waiting_for_transcript_webhook",
                        "meeting_status",
                    ]:
                        filtered_data[k] = v
                    elif v != "":
                        filtered_data[k] = v
            session_data = filtered_data

            # Save session data to SQLite database
            # **Simple Explanation:** We save the session data to our database using the room_name
            # as the key. Later, when Daily.co sends a webhook, we'll use the room_name to look up
            # this data and know where to send the results.
            if session_data:
                from flow.db import save_session_data

                success = save_session_data(room_name, session_data)
                if success:
                    logger.info(
                        f"✅ Session data saved to database for room {room_name}"
                    )
                else:
                    logger.warning(
                        f"⚠️ Failed to save session data to database for room {room_name}"
                    )
            else:
                logger.debug("No session data to save")

        except Exception as e:
            error_msg = f"Failed to create video room: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return self.set_error(state, error_msg)

        return state
