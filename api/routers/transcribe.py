"""
Transcription Router - PailKit API

Handles transcription endpoints for real-time and batch transcription.

Authentication:
- Users provide provider API keys via X-Provider-Auth header
- Format: "Bearer <api_key>" or just "<api_key>"
- Provider specified via X-Provider header

This design allows users to "bring their own key" (BYOK) while maintaining
a unified PailKit API interface. Keys are never stored, keeping the service
lightweight and secure.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from transcribe.config_builder import build_config
from transcribe.providers.base import TranscriptionProvider

router = APIRouter()


def extract_provider_api_key(x_provider_auth: str) -> str:
    """
    Extract API key from X-Provider-Auth header.

    Handles both "Bearer <key>" and raw key formats.

    Args:
        x_provider_auth: The X-Provider-Auth header value

    Returns:
        Extracted API key

    Raises:
        HTTPException: If API key is missing or empty
    """
    api_key = x_provider_auth.strip()
    if api_key.startswith("Bearer "):
        api_key = api_key[7:].strip()

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="X-Provider-Auth header is required. Provide your provider API key.",
        )

    return api_key


# Pydantic models for request validation
class StartTranscriptionRequest(BaseModel):
    """
    Request model for starting a transcription.

    This model defines what information is needed to start a transcription:
    - profile: Which transcription profile to use (e.g., "meeting", "medical")
    - audio_url: Optional URL to audio source (e.g., room recording URL)
    - overrides: Optional custom settings to override profile defaults
    """

    profile: str = "meeting"
    audio_url: str | None = None
    overrides: dict[str, Any] | None = None


class StopTranscriptionRequest(BaseModel):
    """
    Request model for stopping a transcription.

    This model defines what information is needed to stop a transcription:
    - transcription_id: The unique ID returned when transcription was started
    """

    transcription_id: str


def get_provider(provider_name: str, api_key: str) -> TranscriptionProvider:
    """
    Create a transcription provider instance with user-provided API key.

    **Simple Explanation:**
    This function creates a transcription service connection (like Deepgram)
    using the user's API key. Think of it like connecting to a service
    using your account credentials.

    Args:
        provider_name: Provider identifier (e.g., "deepgram", "assemblyai")
        api_key: User's provider API key

    Returns:
        Provider instance

    Raises:
        HTTPException: If provider is unsupported or not yet implemented

    Note:
        Currently no providers are implemented. This will raise an error
        until a provider is added (e.g., Deepgram, AssemblyAI).
    """
    # TODO: Add provider implementations as they are created
    # Normalize provider name to lowercase for consistent matching when providers are added
    _normalized_provider = provider_name.lower().strip()
    # Example:
    # if normalized_provider == "deepgram":
    #     from transcribe.providers.deepgram import DeepgramProvider
    #     return DeepgramProvider(api_key=api_key)

    raise HTTPException(
        status_code=400,
        detail=f"Transcription provider not yet implemented: {provider_name}. "
        "Supported providers will be added in future updates.",
    )


@router.post("/start")
async def start_transcription(
    request: StartTranscriptionRequest,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header(
        "deepgram", description="Provider name (default: deepgram)"
    ),
) -> dict[str, Any]:
    """
    Start a real-time or streaming transcription.

    Begins transcribing audio in real-time from live streams, audio URLs, or direct input.
    Requires X-Provider-Auth header with provider API key and optional X-Provider header.

    Available profiles: meeting, general, medical, finance, podcast.
    Each provider maps profiles to their own model names internally.
    """
    try:
        provider_name = x_provider.lower().strip() if x_provider else "deepgram"
        api_key = extract_provider_api_key(x_provider_auth)
        provider = get_provider(provider_name, api_key)

        # Build transcription configuration from profile and overrides
        # This merges base config + profile config + user overrides
        # Note: Provider-specific model mapping is handled by the provider implementation
        # The router stays provider-agnostic - each provider maps profiles to their own models
        config = build_config(profile=request.profile, overrides=request.overrides)

        # Start the transcription
        result: dict[str, Any] = await provider.start_transcription(
            audio_url=request.audio_url, config=config
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=500, detail=result.get("message", "Unknown error")
            )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        # Handle validation errors from build_config (e.g., invalid profile)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start transcription: {str(e)}"
        ) from e


@router.post("/stop")
async def stop_transcription(
    request: StopTranscriptionRequest,
    x_provider_auth: str = Header(
        ..., description="Provider API key (Bearer token or raw key)"
    ),
    x_provider: str = Header(
        "deepgram", description="Provider name (default: deepgram)"
    ),
) -> dict[str, Any]:
    """
    Stop an active transcription session.

    Stops a transcription started with /start and returns the final transcript.
    Requires X-Provider-Auth header with provider API key.
    """
    try:
        if not request.transcription_id:
            raise HTTPException(status_code=400, detail="transcription_id is required")

        provider_name = x_provider.lower().strip() if x_provider else "deepgram"
        api_key = extract_provider_api_key(x_provider_auth)
        provider = get_provider(provider_name, api_key)

        # Stop the transcription
        result: dict[str, Any] = await provider.stop_transcription(
            request.transcription_id
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=500, detail=result.get("message", "Unknown error")
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop transcription: {str(e)}"
        ) from e
