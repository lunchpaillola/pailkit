"""
Daily Rooms Provider - PailKit API

Handles room creation and management using Daily.co as the provider.

This module implements real REST API calls to Daily.co's API endpoint:
https://api.daily.co/v1/rooms

Key Features:
- Real HTTP requests using httpx async client
- Profile-based room creation with opinionated configurations
- Comprehensive config mapping from PailKit to Daily format
- Complete error handling and response parsing
"""

from typing import Any

import httpx

from rooms.config_builder import build_config


class DailyRooms:
    """Daily.co implementation for room management."""

    def __init__(self, api_key: str):
        """
        Initialize the Daily Rooms provider.

        Args:
            api_key: Daily.co API key (can be just the token or "Bearer <token>" format)
        """
        self.api_key = api_key
        self.provider = "daily"
        self.base_url = "https://api.daily.co/v1"

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for Daily API requests."""
        # Ensure the Authorization header has "Bearer " prefix
        auth_header = self.api_key
        if not auth_header.startswith("Bearer "):
            auth_header = f"Bearer {self.api_key}"

        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": auth_header
        }

    def to_daily_config(self, pail_config: dict[str, Any]) -> dict[str, Any]:
        """
        Translate Pail Kit config to Daily.co API parameters.

        This function takes our provider-agnostic configuration and
        converts it to the specific format that Daily.co expects.

        Args:
            pail_config: Pail Kit configuration dictionary

        Returns:
            Dictionary with Daily.co API parameters
        """
        # Extract the different sections of our config
        media = pail_config.get("media", {})
        capabilities = pail_config.get("capabilities", {})
        interaction = pail_config.get("interaction", {})
        access = pail_config.get("access", {})
        lifespan = pail_config.get("lifespan", {})
        localization = pail_config.get("localization", {})

        # Build Daily's properties object
        daily_properties: dict[str, Any] = {}

        # Map media settings
        # Note: Daily doesn't have explicit video/audio toggles for rooms
        # These are controlled client-side. But we can disable screenshare if needed.
        if not media.get("screenshare_capable", True):
            daily_properties["enable_screenshare"] = False
        else:
            daily_properties["enable_screenshare"] = True
        
        # Map video setting: if video is False (audio-only), set start_video_off to true
        # This ensures participants join with video off by default
        if media.get("video") is False:
            daily_properties["start_video_off"] = True

        # Map capability settings to Daily's properties
        daily_properties["enable_chat"] = capabilities.get("chat", False)
        screenshare_enabled = (
            capabilities.get("screenshare", True) and
            media.get("screenshare_capable", True)
        )
        daily_properties["enable_screenshare"] = screenshare_enabled

        # Map recording setting
        # If recording is explicitly False, ensure it's disabled
        # If recording is True, enable cloud recording
        recording = capabilities.get("recording")
        if recording is False:
            daily_properties["enable_recording"] = False
        elif recording is True:
            daily_properties["enable_recording"] = "cloud"
        # If recording is None/not set, use Daily's default (no recording)

        # Map interaction settings
        daily_properties["enable_prejoin_ui"] = interaction.get("prejoin", True)
        
        # Map broadcast mode to owner_only_broadcast
        # When broadcast_mode is True, only the room owner can broadcast (presenter mode)
        # This is used for webinars, presentations, and live streams
        broadcast_mode = interaction.get("broadcast_mode", False)
        daily_properties["owner_only_broadcast"] = bool(broadcast_mode)

        # Map capabilities that have Daily equivalents
        if capabilities.get("breakout_rooms", False):
            daily_properties["enable_breakout_rooms"] = True

        # Map transcription settings
        if capabilities.get("transcription", False):
            daily_properties["enable_transcription_storage"] = True
            daily_properties["auto_transcription_settings"] = {
                "language": localization.get("lang", "en"),
                "model": "nova-2",
                "punctuate": True,  # Smart default
                "profanity_filter": False,  # Don't censor by default
            }

        if capabilities.get("live_captions", False):
            daily_properties["enable_live_captions_ui"] = True

        # Map RTMP streaming
        # Daily.co RTMP streaming configuration
        # RTMP URL can be provided via overrides: {"capabilities": {"rtmp_url": "rtmp://..."}}
        if capabilities.get("rtmp_streaming", False):
            rtmp_url = capabilities.get("rtmp_url")
            if rtmp_url:
                # Configure RTMP streaming with provided URL
                # Daily.co uses rtmp_ingress property for RTMP streaming to external platforms
                daily_properties["rtmp_ingress"] = {
                    "rtmp_url": rtmp_url
                }
            else:
                # Placeholder RTMP URL - user will verify later
                # Format: rtmp://[server]/app/stream_key
                # This is a placeholder that can be updated via room update API
                daily_properties["rtmp_ingress"] = {
                    "rtmp_url": "rtmp://placeholder.rtmp.server/app/stream_key"
                }

        # Map access settings
        privacy = access.get("privacy", "public")
        max_participants = access.get("max_participants")

        # Map lifespan settings
        if lifespan.get("expires_in") is not None:
            # expires_in is in seconds, Daily expects timestamp
            import time
            daily_properties["exp"] = int(time.time()) + lifespan["expires_in"]

        if lifespan.get("eject_at_expiry", False):
            daily_properties["eject_at_room_exp"] = True

        # Build the request payload, only including fields with actual values
        result = {
            "properties": daily_properties,
            "privacy": privacy
        }

        # Only include max_participants if it's actually set (not None)
        if max_participants is not None:
            result["max_participants"] = max_participants

        return result

    async def create_room(
        self,
        profile: str = "conversation",
        overrides: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Create a room using Daily.co with profile-based configuration.

        Args:
            profile: Profile name (e.g., "conversation", "broadcast")
            overrides: Optional configuration overrides

        Returns:
            Dictionary with room creation result
        """
        try:
            # Build the configuration using our profile system
            pail_config = build_config(profile=profile, overrides=overrides)

            # Translate to Daily's format
            daily_config = self.to_daily_config(pail_config)

            # Make the actual API call to Daily.co
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/rooms",
                    headers=self._get_headers(),
                    json=daily_config,
                    timeout=30.0
                )

                response.raise_for_status()
                result = response.json()

                # Extract room name from URL (Daily.co uses name for delete operations)
                room_url = result.get("url", "")
                room_name = ""
                if room_url:
                    # URL format: https://domain.daily.co/[name]
                    room_name = room_url.split("/")[-1]

                return {
                    "success": True,
                    "room_id": result.get("id"),
                    "room_name": room_name,  # Short name used for API operations
                    "provider": self.provider,
                    "room_url": room_url,
                    "created_at": result.get("created_at"),
                    "config": result.get("config", {}),
                    "privacy": result.get("privacy"),
                    "profile": profile,
                    "message": "Room created successfully"
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
                "room_id": "",
                "provider": self.provider,
                "message": f"Daily API error: {error_detail}"
            }
        except Exception as e:
            return {
                "success": False,
                "room_id": "",
                "provider": self.provider,
                "message": f"Failed to create room: {str(e)}"
            }

    async def get_room(self, room_name: str) -> dict[str, Any]:
        """
        Get room details from Daily.co.

        Args:
            room_name: Room name (short identifier, not UUID)
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/rooms/{room_name}",
                    headers=self._get_headers(),
                    timeout=30.0
                )

                response.raise_for_status()
                result = response.json()

                return {
                    "success": True,
                    "room_name": room_name,
                    "provider": self.provider,
                    "room_url": result.get("url"),
                    "config": result.get("config", {}),
                    "message": "Room details retrieved successfully"
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
                "room_name": room_name,
                "provider": self.provider,
                "message": f"Daily API error: {error_detail}"
            }
        except Exception as e:
            return {
                "success": False,
                "room_name": room_name,
                "provider": self.provider,
                "message": f"Failed to get room: {str(e)}"
            }

    async def delete_room(self, room_name: str) -> dict[str, Any]:
        """
        Delete a room from Daily.co.

        Args:
            room_name: Room name (short identifier, not UUID)
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/rooms/{room_name}",
                    headers=self._get_headers(),
                    timeout=30.0
                )

                response.raise_for_status()

                return {
                    "success": True,
                    "room_name": room_name,
                    "provider": self.provider,
                    "message": "Room deleted successfully"
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
                "room_name": room_name,
                "provider": self.provider,
                "message": f"Daily API error: {error_detail}"
            }
        except Exception as e:
            return {
                "success": False,
                "room_name": room_name,
                "provider": self.provider,
                "message": f"Failed to delete room: {str(e)}"
            }
