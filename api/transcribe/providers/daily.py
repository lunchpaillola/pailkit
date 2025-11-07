# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Daily Transcription Provider - PailKit API

Handles real-time transcription for Daily.co rooms.

Implements Daily.co transcription API endpoints:
- POST /v1/rooms/{room_name}/transcription/start
- POST /v1/rooms/{room_name}/transcription/stop
"""

from typing import Any
from urllib.parse import urlparse

import httpx

from transcribe.providers.base import TranscriptionProvider

# Maps PailKit profiles to Daily.co transcription models
MODEL_MAPPING: dict[str, str] = {
    "general": "nova-3",
    "meeting": "nova-3-meeting",
    "medical": "nova-3-medical",
    "finance": "nova-2-finance",
}


class DailyTranscription(TranscriptionProvider):
    """Daily.co implementation for real-time transcription."""

    def __init__(self, api_key: str):
        """
        Initialize the Daily Transcription provider.

        Args:
            api_key: Daily.co API key (can be just the token or "Bearer <token>" format)
        """
        super().__init__(api_key)
        self.provider = "daily"
        self.base_url = "https://api.daily.co/v1"

    def _get_headers(self) -> dict[str, str]:
        """
        Get HTTP headers for Daily API requests.

        Returns:
            Dictionary with HTTP headers including Authorization
        """
        auth_header = self.api_key
        if not auth_header.startswith("Bearer "):
            auth_header = f"Bearer {self.api_key}"

        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }

    def _extract_room_name(self, audio_url: str | None) -> str:
        """
        Extract room name from Daily.co room URL.

        Daily.co room URLs have the format: https://domain.daily.co/{room_name}

        Args:
            audio_url: Daily.co room URL (e.g., "https://domain.daily.co/abc123")

        Returns:
            Room name extracted from URL

        Raises:
            ValueError: If URL is invalid or not a Daily.co URL
        """
        if not audio_url:
            raise ValueError("audio_url is required for Daily.co transcription")

        parsed = urlparse(audio_url)
        path = parsed.path.strip("/")
        if not path:
            raise ValueError(
                f"Invalid Daily.co room URL: {audio_url}. "
                "Expected format: https://domain.daily.co/{room_name}"
            )

        return path

    def _get_model_from_profile(self, config: dict[str, Any]) -> str:
        """
        Get Daily.co transcription model from PailKit profile.

        Args:
            config: Transcription configuration from build_config()

        Returns:
            Daily.co model name (e.g., "nova-3-meeting")
        """
        profile = config.get("profile", "meeting")
        model = MODEL_MAPPING.get(profile, MODEL_MAPPING["meeting"])

        return model

    def _to_daily_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Translate PailKit transcription config to Daily.co API format.

        Args:
            config: PailKit transcription configuration

        Returns:
            Dictionary with Daily.co transcription API parameters
        """
        model = self._get_model_from_profile(config)
        language = config.get("language", "en")
        features = config.get("features", {})
        punctuate = features.get("punctuate", True)
        profanity_filter = features.get("profanity_filter", False)

        daily_config = {
            "model": model,
            "language": language,
            "punctuate": punctuate,
            "profanity_filter": profanity_filter,
        }

        return daily_config

    async def start_transcription(
        self,
        audio_url: str | None = None,
        audio_stream: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Start real-time transcription for a Daily.co room.

        Args:
            audio_url: Daily.co room URL (e.g., "https://domain.daily.co/abc123")
            audio_stream: Not used for Daily.co (transcription is room-based)
            config: Transcription configuration from build_config()

        Returns:
            Dictionary with transcription result including success, transcription_id,
            provider, and message.
        """
        try:
            if not audio_url:
                return {
                    "success": False,
                    "transcription_id": "",
                    "provider": self.provider,
                    "message": "audio_url is required for Daily.co transcription. "
                    "Provide a Daily.co room URL (e.g., https://domain.daily.co/room-name)",
                }

            room_name = self._extract_room_name(audio_url)

            if config is None:
                config = {}

            daily_config = self._to_daily_config(config)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/rooms/{room_name}/transcription/start",
                    headers=self._get_headers(),
                    json=daily_config,
                    timeout=30.0,
                )

                response.raise_for_status()

                return {
                    "success": True,
                    "transcription_id": room_name,
                    "provider": self.provider,
                    "message": "Transcription started successfully",
                    "room_name": room_name,
                    "config": daily_config,
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
                "transcription_id": "",
                "provider": self.provider,
                "message": f"Daily API error: {error_detail}",
            }
        except ValueError as e:
            return {
                "success": False,
                "transcription_id": "",
                "provider": self.provider,
                "message": f"Validation error: {str(e)}",
            }
        except Exception as e:
            return {
                "success": False,
                "transcription_id": "",
                "provider": self.provider,
                "message": f"Failed to start transcription: {str(e)}",
            }

    async def stop_transcription(self, transcription_id: str) -> dict[str, Any]:
        """
        Stop an active transcription session for a Daily.co room.

        For Daily.co, the transcription_id is the room_name.

        Args:
            transcription_id: The room name (returned from start_transcription())

        Returns:
            Dictionary with stop result including success, transcription_id,
            provider, and message. final_transcript is None (not available for
            Daily.co real-time transcription).
        """
        try:
            if not transcription_id:
                return {
                    "success": False,
                    "transcription_id": "",
                    "provider": self.provider,
                    "message": "transcription_id (room_name) is required",
                }

            room_name = transcription_id

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/rooms/{room_name}/transcription/stop",
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                response.raise_for_status()

                return {
                    "success": True,
                    "transcription_id": room_name,
                    "provider": self.provider,
                    "message": "Transcription stopped successfully",
                    "room_name": room_name,
                    # Daily.co real-time transcription doesn't return a final transcript
                    # Users must retrieve transcripts via Daily.co's transcript API
                    "final_transcript": None,
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
                "transcription_id": transcription_id,
                "provider": self.provider,
                "message": f"Daily API error: {error_detail}",
            }
        except Exception as e:
            return {
                "success": False,
                "transcription_id": transcription_id,
                "provider": self.provider,
                "message": f"Failed to stop transcription: {str(e)}",
            }

    async def submit_batch_job(
        self, audio_url: str, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Submit a batch transcription job (not supported by Daily.co).

        Daily.co transcription is real-time only and room-based.

        Args:
            audio_url: URL to audio file (not used)
            config: Transcription configuration (not used)

        Returns:
            Dictionary with error result indicating batch jobs are not supported
        """
        return {
            "success": False,
            "job_id": "",
            "provider": self.provider,
            "status": "unsupported",
            "message": "Batch transcription is not supported by Daily.co. "
            "Daily.co transcription is real-time only for active rooms. "
            "Use start_transcription() with a Daily.co room URL instead.",
        }

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """
        Get batch job status (not supported by Daily.co).

        Daily.co transcription is real-time only and room-based.

        Args:
            job_id: Job ID (not used)

        Returns:
            Dictionary with error result indicating batch jobs are not supported
        """
        return {
            "success": False,
            "job_id": job_id,
            "status": "unsupported",
            "transcript": None,
            "provider": self.provider,
            "message": "Batch transcription is not supported by Daily.co. "
            "Daily.co transcription is real-time only for active rooms.",
        }
