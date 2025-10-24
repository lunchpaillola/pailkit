"""
Rooms Router - PailKit API

Handles room creation for video, audio, and live collaboration.
"""

import os
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from providers.rooms.daily import DailyRooms

router = APIRouter()

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


def get_provider(provider_name: str):
    """Get the appropriate provider instance."""
    if provider_name == "daily":
        return daily_provider
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")


@router.post("/create")
async def create_room(room_data: Dict[str, Any]):
    """
    Create a new room for video, audio, or live collaboration.
    
    This is the first building block of PailKit - a single API call
    to spin up a new video or audio room.
    """
    try:
        # Extract parameters
        name = room_data.get("name", "Untitled Room")
        room_type = room_data.get("room_type", "video")
        privacy = room_data.get("privacy", "public")
        provider_name = room_data.get("provider", "daily")
        
        # Get the appropriate provider
        provider = get_provider(provider_name)
        
        # Create the room
        result = await provider.create_room(name, room_type, privacy)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}")
