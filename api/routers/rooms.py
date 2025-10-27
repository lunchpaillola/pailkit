"""
Rooms Router - PailKit API

Handles room creation for video, audio, and live collaboration.
"""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from providers.rooms.daily import DailyRooms

router = APIRouter()


# Pydantic models for request validation
class RoomCreateRequest(BaseModel):
    """Request model for creating a room."""
    profile: str = "conversation"
    overrides: dict[str, Any] | None = None
    provider: str | None = "daily"


# TODO: Unified API key handling
# Since this is a unified API, users need to provide their own API keys
# Need to figure out how users will provide API keys:
# - User provisioning system?
# - Open API key management?

# For now, using environment variable for development
daily_api_key = os.getenv("DAILY_API_KEY")
if not daily_api_key:
    raise ValueError("DAILY_API_KEY environment variable is required for development")

daily_provider = DailyRooms(api_key=daily_api_key)


def get_provider(provider_name: str) -> DailyRooms:
    """Get the appropriate provider instance."""
    if provider_name == "daily":
        return daily_provider
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")


@router.post("/create")
async def create_room(request: RoomCreateRequest) -> dict[str, Any]:
    """
    Create a new room for video, audio, or live collaboration.

    This is the first building block of PailKit - a single API call
    to spin up a new video or audio room using opinionated profiles.

    **Request format:**
    ```json
    {
      "profile": "broadcast",
      "overrides": {"capabilities": {"chat": false}}
    }
    ```

    **Available profiles:**
    - `conversation` - Standard video chat
    - `audio_room` - Audio-only conversation
    - `broadcast` - One-to-many presentation
    - `podcast` - Audio recording session
    - `live_stream` - Stream to external platforms
    - `workshop` - Interactive collaborative session
    """
    try:
        # Get the appropriate provider
        provider = get_provider(request.provider)

        # Create the room with profile-based API
        result = await provider.create_room(
            profile=request.profile,
            overrides=request.overrides
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}")


@router.delete("/delete/{room_name}")
async def delete_room(room_name: str, provider: str = "daily") -> dict[str, Any]:
    """
    Delete a room.

    This endpoint allows you to clean up rooms after use.

    **Parameters:**
    - `room_name` - The short name of the room to delete (from room_url)
    - `provider` - The provider (default: "daily")

    **Note:** Use the room_name from the URL, not the room_id UUID.
    Example: For room_url "https://domain.daily.co/abc123", use "abc123"
    """
    try:
        # Get the appropriate provider
        provider_instance = get_provider(provider)

        # Delete the room
        result = await provider_instance.delete_room(room_name)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete room: {str(e)}")
