"""
Rooms Router - PailKit API

Handles room creation for video, audio, and live collaboration.

Authentication:
- Users provide provider API keys via X-Provider-Auth header
- Format: "Bearer <api_key>" or just "<api_key>"
- Provider specified via X-Provider header (default: "daily")

This design allows users to "bring their own key" (BYOK) while maintaining
a unified PailKit API interface. Keys are never stored, keeping the service
lightweight and secure.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from providers.rooms.daily import DailyRooms

router = APIRouter()


# Pydantic models for request validation
class RoomCreateRequest(BaseModel):
    """
    Request model for creating a room.

    Note: Provider is specified via X-Provider header, not in the request body.
    This keeps authentication and provider selection together in headers.
    """
    profile: str = "conversation"
    overrides: dict[str, Any] | None = None


def get_provider(provider_name: str, api_key: str) -> DailyRooms:
    """
    Create a provider instance with user-provided API key.

    Args:
        provider_name: Provider identifier (e.g., "daily") - will be normalized to lowercase
        api_key: User's provider API key

    Returns:
        Provider instance

    Raises:
        HTTPException: If provider is unsupported
    """
    # Normalize provider name to lowercase for consistent matching
    normalized_provider = provider_name.lower().strip()

    if normalized_provider == "daily":
        return DailyRooms(api_key=api_key)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider_name}. Supported: daily"
        )


@router.post("/create")
async def create_room(
    request: RoomCreateRequest,
    x_provider_auth: str = Header(..., description="Provider API key (Bearer token or raw key)"),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """
    Create a new room for video, audio, or live collaboration.

    This is the first building block of PailKit - a single API call
    to spin up a new video or audio room using opinionated profiles.

    **Authentication:**
    Provide your provider API key via the `X-Provider-Auth` header:
    - Format: `Bearer <your-api-key>` or just `<your-api-key>`
    - For Daily.co: Get your API key from https://dashboard.daily.co/developers

    **Providers:**
    Specify provider via `X-Provider` header (default: "daily")
    - `daily` - Daily.co video rooms

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

    **Example:**
    ```bash
    curl -X POST https://api.pailkit.com/api/rooms/create \\
      -H "X-Provider-Auth: Bearer your-daily-api-key" \\
      -H "X-Provider: daily" \\
      -H "Content-Type: application/json" \\
      -d '{"profile": "conversation"}'
    ```
    """
    try:
        # Provider comes from X-Provider header (defaults to "daily" if not provided)
        # This ensures provider selection is consistent with authentication (both in headers)
        provider_name = x_provider.lower().strip() if x_provider else "daily"

        # Extract API key from header (handle both "Bearer <key>" and raw key formats)
        api_key = x_provider_auth.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="X-Provider-Auth header is required. Provide your provider API key."
            )

        # Create provider instance with user's API key
        provider = get_provider(provider_name, api_key)

        # Create the room with profile-based API
        result: dict[str, Any] = await provider.create_room(
            profile=request.profile,
            overrides=request.overrides
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}") from e


@router.delete("/delete/{room_name}")
async def delete_room(
    room_name: str,
    x_provider_auth: str = Header(..., description="Provider API key (Bearer token or raw key)"),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """
    Delete a room.

    This endpoint allows you to clean up rooms after use.

    **Authentication:**
    Provide your provider API key via the `X-Provider-Auth` header
    (same key used to create the room).

    **Parameters:**
    - `room_name` - The short name of the room to delete (from room_url)

    **Note:** Use the room_name from the URL, not the room_id UUID.
    Example: For room_url "https://domain.daily.co/abc123", use "abc123"

    **Example:**
    ```bash
    curl -X DELETE https://api.pailkit.com/api/rooms/delete/abc123 \\
      -H "X-Provider-Auth: Bearer your-daily-api-key" \\
      -H "X-Provider: daily"
    ```
    """
    try:
        # Provider comes from X-Provider header (defaults to "daily" if not provided)
        provider_name = x_provider.lower().strip() if x_provider else "daily"

        # Extract API key from header (handle both "Bearer <key>" and raw key formats)
        api_key = x_provider_auth.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="X-Provider-Auth header is required. Provide your provider API key."
            )

        # Create provider instance with user's API key
        provider_instance = get_provider(provider_name, api_key)

        # Delete the room
        result: dict[str, Any] = await provider_instance.delete_room(room_name)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete room: {str(e)}") from e


@router.get("/get/{room_name}")
async def get_room(
    room_name: str,
    x_provider_auth: str = Header(..., description="Provider API key (Bearer token or raw key)"),
    x_provider: str = Header("daily", description="Provider name (default: daily)"),
) -> dict[str, Any]:
    """
    Get room details.

    Retrieve configuration and status information for an existing room.

    **Authentication:**
    Provide your provider API key via the `X-Provider-Auth` header
    (same key used to create the room).

    **Parameters:**
    - `room_name` - The short name of the room (from room_url)

    **Example:**
    ```bash
    curl -X GET https://api.pailkit.com/api/rooms/get/abc123 \\
      -H "X-Provider-Auth: Bearer your-daily-api-key" \\
      -H "X-Provider: daily"
    ```
    """
    try:
        # Provider comes from X-Provider header (defaults to "daily" if not provided)
        provider_name = x_provider.lower().strip() if x_provider else "daily"

        # Extract API key from header (handle both "Bearer <key>" and raw key formats)
        api_key = x_provider_auth.strip()
        if api_key.startswith("Bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="X-Provider-Auth header is required. Provide your provider API key."
            )

        # Create provider instance with user's API key
        provider_instance = get_provider(provider_name, api_key)

        # Get the room details
        result: dict[str, Any] = await provider_instance.get_room(room_name)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get room: {str(e)}") from e
